"""Operações por comanda: READ COMMITTED, locks e um único commit por escrita.

Não ativa controle financeiro, não concilia legado e não consulta faturamento.
Exige sessão da requisição sem alterações pendentes. Consultas mantêm locks
compartilhados até o chamador encerrar a transação; não fazem commit.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Agendamento, Comanda, ItemComanda, Usuario, PerfilEnum,
    ControleFinanceiroComanda, PagamentoComanda, EstornoPagamento,
    FechamentoFinanceiroComanda, SituacaoFinanceiraEnum,
)
from app.services import filiais
from app.services.errors import SemPermissao, RecursoNaoEncontrado
from app.services.financeiro_errors import (
    AcessoFinanceiroNegado, ComandaFinanceiraNaoEncontrada, ConflitoIdempotenciaFinanceira,
    DadosFinanceirosInconsistentes, EntradaFinanceiraInvalida, EstadoFinanceiroIncompativel,
    HistoricoFinanceiroNaoVerificado, LimiteEstornoExcedido, SaldoInsuficiente,
)
from app.services.permissoes_financeiras import autorizar_recebimento_ou_fechamento
from app.services.persistencia import transacao_escrita
from app.services.regras_financeiras import (
    FORMAS, FUSO, LIMITE, data_efetiva, fingerprint, identificador,
    motivo_auditavel, validar_janela, valor_monetario,
)

ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ResumoFinanceiro:
    comanda_id: UUID
    filial_id: UUID
    situacao: SituacaoFinanceiraEnum
    total: Decimal
    pagamentos: Decimal | None
    estornos: Decimal | None
    recebido_liquido: Decimal | None
    saldo: Decimal | None


@dataclass(frozen=True)
class PagamentoRegistrado:
    id: UUID
    comanda_id: UUID
    filial_id: UUID
    valor: Decimal
    forma: str
    recebido_em: datetime
    registrado_em: datetime
    registrado_por: UUID
    chave_idempotencia: UUID


@dataclass(frozen=True)
class EstornoRegistrado:
    id: UUID
    pagamento_id: UUID
    comanda_id: UUID
    filial_id: UUID
    valor: Decimal
    motivo: str
    efetivado_em: datetime
    registrado_em: datetime
    registrado_por: UUID
    chave_idempotencia: UUID


@dataclass(frozen=True)
class FechamentoRegistrado:
    comanda_id: UUID
    filial_id: UUID
    total: Decimal
    recebido_liquido: Decimal
    motivo: str | None
    registrado_em: datetime
    registrado_por: UUID
    chave_idempotencia: UUID


def _sessao_limpa(db):
    if db.new or db.dirty or db.deleted:
        raise EntradaFinanceiraInvalida("Use sessão sem alterações pendentes para operações financeiras")


@contextmanager
def _escrita(db):
    _sessao_limpa(db)
    with transacao_escrita(db), db.no_autoflush:
        yield


def _contexto(db, usuario, comanda_id, filial_id, *, leitura=False, estorno=False):
    identificador(comanda_id)
    if filial_id is not None:
        identificador(filial_id)
    if db.connection().get_isolation_level() != "READ COMMITTED":
        raise EntradaFinanceiraInvalida("Operação financeira exige READ COMMITTED")
    try:
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        # Valida atividade/perfil antes de usar o escopo de consultas existente.
        autorizar_recebimento_ou_fechamento(usuario, usuario.id)
        if estorno and usuario.perfil != PerfilEnum.ADMIN:
            raise AcessoFinanceiroNegado("Somente ADMIN pode realizar estornos")
    except SemPermissao:
        raise AcessoFinanceiroNegado("Usuário sem permissão financeira ativa") from None
    try:
        # escrita=True restringe também a leitura financeira do chefe às próprias.
        contexto = db.execute(select(Comanda.agendamento_id, Comanda.filial_id).where(
            Comanda.id == comanda_id, *filiais.filtro_acesso(usuario, Comanda, escrita=True),
        )).first()
        if contexto is None or (filial_id is not None and filial_id != contexto.filial_id):
            raise ComandaFinanceiraNaoEncontrada("Comanda não encontrada")
        filiais.resolver_filial(db, usuario, contexto.filial_id, bloquear=True)
        agendamento = db.scalar(select(Agendamento).where(
            Agendamento.id == contexto.agendamento_id, Agendamento.filial_id == contexto.filial_id,
        ).execution_options(populate_existing=True).with_for_update(read=leitura))
        comanda = db.scalar(select(Comanda).where(
            Comanda.id == comanda_id, Comanda.filial_id == contexto.filial_id,
        ).execution_options(populate_existing=True).with_for_update(read=leitura))
        if comanda is None or agendamento is None:
            raise ComandaFinanceiraNaoEncontrada("Comanda não encontrada")
        autorizar_recebimento_ou_fechamento(usuario, comanda.barbeiro_id)
    except (SemPermissao, RecursoNaoEncontrado):
        raise ComandaFinanceiraNaoEncontrada("Comanda não encontrada") from None
    if (comanda.agendamento_id, comanda.filial_id, comanda.cliente_id, comanda.barbeiro_id) != (
        agendamento.id, agendamento.filial_id, agendamento.cliente_id, agendamento.barbeiro_id,
    ):
        raise DadosFinanceirosInconsistentes("Contexto operacional inconsistente")
    return usuario, agendamento, comanda


def _registro(db, modelo, comanda, **filtros):
    return db.scalar(select(modelo).filter_by(
        comanda_id=comanda.id, filial_id=comanda.filial_id, **filtros,
    ).execution_options(populate_existing=True))


def _total(db, comanda):
    # O pai já está bloqueado. Não exigir UPDATE nos itens (runtime só lê/cria).
    # Qualquer futuro editor de itens deve adquirir o mesmo lock da comanda.
    itens = db.execute(select(ItemComanda.quantidade, ItemComanda.preco_unitario).where(
        ItemComanda.comanda_id == comanda.id,
    ).order_by(ItemComanda.id)).all()
    total = ZERO
    for quantidade, preco in itens:
        try:
            if not isinstance(quantidade, int) or quantidade <= 0:
                raise EntradaFinanceiraInvalida("Quantidade inválida")
            total += quantidade * valor_monetario(preco, permitir_zero=True)
        except EntradaFinanceiraInvalida:
            raise DadosFinanceirosInconsistentes("Itens financeiros inválidos") from None
        if total > LIMITE:
            raise DadosFinanceirosInconsistentes("Total fora da faixa monetária")
    return total


def _somar(db, modelo, comanda, **filtros):
    return db.scalar(select(func.coalesce(func.sum(modelo.valor), ZERO)).filter_by(
        comanda_id=comanda.id, filial_id=comanda.filial_id, **filtros,
    ))


def _resumo(db, comanda):
    total = _total(db, comanda)
    if _registro(db, ControleFinanceiroComanda, comanda) is None:
        return ResumoFinanceiro(comanda.id, comanda.filial_id,
                               SituacaoFinanceiraEnum.NAO_VERIFICADO, total, None, None, None, None)
    pagos = _somar(db, PagamentoComanda, comanda)
    estornos = _somar(db, EstornoPagamento, comanda)
    liquido = pagos - estornos
    if not ZERO <= liquido <= total:
        raise DadosFinanceirosInconsistentes("Recebimentos incompatíveis com os itens")
    fechamento = _registro(db, FechamentoFinanceiroComanda, comanda)
    if fechamento and (fechamento.total != total or fechamento.recebido_liquido != liquido):
        raise DadosFinanceirosInconsistentes("Histórico diverge do fechamento financeiro")
    return ResumoFinanceiro(comanda.id, comanda.filial_id,
        SituacaoFinanceiraEnum.FECHADO if fechamento else SituacaoFinanceiraEnum.ABERTO,
        total, pagos, estornos, liquido, total - liquido)


def _permitir_nova_operacao(resumo, agendamento, comanda):
    if resumo.situacao == SituacaoFinanceiraEnum.NAO_VERIFICADO:
        raise HistoricoFinanceiroNaoVerificado("Conciliação financeira explícita necessária")
    if resumo.situacao == SituacaoFinanceiraEnum.FECHADO:
        raise EstadoFinanceiroIncompativel("Comanda financeiramente fechada")
    if agendamento.status != "concluido" or comanda.status != "fechada":
        raise EstadoFinanceiroIncompativel("Atendimento ainda não concluído operacionalmente")


def _repeticao(registro, esperado):
    if registro.fingerprint != esperado:
        raise ConflitoIdempotenciaFinanceira("Chave já utilizada com outro conteúdo")


def _dto(registro, tipo):
    return tipo(**{campo: getattr(registro, campo) for campo in tipo.__dataclass_fields__})


def _inserir(db, registro, tipo):
    db.add(registro)
    db.flush()
    # Dentro da transação: falha de leitura ainda reverte o INSERT. Nada após COMMIT.
    db.refresh(registro)
    return _dto(registro, tipo)


def _agora(db):
    return db.scalar(select(func.clock_timestamp())).astimezone(FUSO)


def consultar_situacao(comanda_id: UUID, db: Session, usuario: Usuario,
                       filial_id: UUID | None = None) -> ResumoFinanceiro:
    _sessao_limpa(db)
    with db.no_autoflush:
        _, _, comanda = _contexto(db, usuario, comanda_id, filial_id, leitura=True)
        return _resumo(db, comanda)


def registrar_pagamento(comanda_id: UUID, *, valor: Decimal, forma: str,
                        recebido_em: datetime, chave_idempotencia: UUID,
                        db: Session, usuario: Usuario, filial_id: UUID | None = None) -> PagamentoRegistrado:
    with _escrita(db):
        usuario, agendamento, comanda = _contexto(db, usuario, comanda_id, filial_id)
        chave = identificador(chave_idempotencia)
        valor = valor_monetario(valor)
        if forma not in FORMAS:
            raise EntradaFinanceiraInvalida("Forma de pagamento inválida")
        efetiva = data_efetiva(recebido_em)
        fp = fingerprint("pagamento", comanda_id=comanda.id, valor=valor, forma=forma, recebido_em=efetiva)
        anterior = _registro(db, PagamentoComanda, comanda, chave_idempotencia=chave)
        if anterior is not None:
            _repeticao(anterior, fp)
            resultado = _dto(anterior, PagamentoRegistrado)
        else:
            resumo = _resumo(db, comanda)
            _permitir_nova_operacao(resumo, agendamento, comanda)
            validar_janela(efetiva, _agora(db), admin=usuario.perfil == PerfilEnum.ADMIN)
            if valor > resumo.saldo:
                raise SaldoInsuficiente("Recebimento superior ao saldo devido")
            resultado = _inserir(db, PagamentoComanda(comanda_id=comanda.id, filial_id=comanda.filial_id,
                valor=valor, forma=forma, recebido_em=efetiva, registrado_por=usuario.id,
                chave_idempotencia=chave, fingerprint=fp), PagamentoRegistrado)
    return resultado


def registrar_estorno(comanda_id: UUID, *, pagamento_id: UUID, valor: Decimal,
                      motivo: str, efetivado_em: datetime, chave_idempotencia: UUID,
                      db: Session, usuario: Usuario, filial_id: UUID | None = None) -> EstornoRegistrado:
    with _escrita(db):
        usuario, agendamento, comanda = _contexto(db, usuario, comanda_id, filial_id, estorno=True)
        chave = identificador(chave_idempotencia)
        pagamento_id = identificador(pagamento_id)
        valor = valor_monetario(valor)
        motivo = motivo_auditavel(motivo, obrigatorio=True)
        efetiva = data_efetiva(efetivado_em)
        fp = fingerprint("estorno", comanda_id=comanda.id, pagamento_id=pagamento_id,
                         valor=valor, motivo=motivo, efetivado_em=efetiva)
        anterior = _registro(db, EstornoPagamento, comanda, chave_idempotencia=chave)
        if anterior is not None:
            _repeticao(anterior, fp)
            resultado = _dto(anterior, EstornoRegistrado)
        else:
            resumo = _resumo(db, comanda)
            _permitir_nova_operacao(resumo, agendamento, comanda)
            pagamento = _registro(db, PagamentoComanda, comanda, id=pagamento_id)
            if pagamento is None:
                raise ComandaFinanceiraNaoEncontrada("Pagamento não encontrado")
            validar_janela(efetiva, _agora(db), admin=True)
            if efetiva < pagamento.recebido_em:
                raise EntradaFinanceiraInvalida("Estorno não pode anteceder o recebimento original")
            ja_estornado = _somar(db, EstornoPagamento, comanda, pagamento_id=pagamento_id)
            if valor > pagamento.valor - ja_estornado:
                raise LimiteEstornoExcedido("Estorno superior ao disponível no pagamento")
            resultado = _inserir(db, EstornoPagamento(comanda_id=comanda.id, filial_id=comanda.filial_id,
                pagamento_id=pagamento_id, valor=valor, motivo=motivo, efetivado_em=efetiva,
                registrado_por=usuario.id, chave_idempotencia=chave, fingerprint=fp), EstornoRegistrado)
    return resultado


def fechar_comanda(comanda_id: UUID, *, chave_idempotencia: UUID, db: Session,
                    usuario: Usuario, motivo: str | None = None,
                    filial_id: UUID | None = None) -> FechamentoRegistrado:
    with _escrita(db):
        usuario, agendamento, comanda = _contexto(db, usuario, comanda_id, filial_id)
        chave = identificador(chave_idempotencia)
        motivo = motivo_auditavel(motivo)
        fp = fingerprint("fechamento", comanda_id=comanda.id, motivo=motivo)
        anterior = _registro(db, FechamentoFinanceiroComanda, comanda)
        if anterior is not None:
            if anterior.chave_idempotencia != chave:
                raise EstadoFinanceiroIncompativel("Comanda financeiramente fechada")
            _repeticao(anterior, fp)
            resultado = _dto(anterior, FechamentoRegistrado)
        else:
            resumo = _resumo(db, comanda)
            _permitir_nova_operacao(resumo, agendamento, comanda)
            if resumo.saldo != ZERO:
                raise SaldoInsuficiente("Fechamento exige saldo quitado")
            if resumo.total == ZERO:
                motivo = motivo_auditavel(motivo, obrigatorio=True)
            resultado = _inserir(db, FechamentoFinanceiroComanda(comanda_id=comanda.id,
                filial_id=comanda.filial_id, total=resumo.total, recebido_liquido=resumo.recebido_liquido,
                motivo=motivo, registrado_por=usuario.id, chave_idempotencia=chave,
                fingerprint=fp), FechamentoRegistrado)
    return resultado
