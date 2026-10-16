"""Operações de agendamento, sem dependência da camada HTTP.

Cada operação confirma uma única vez pela fronteira transacional compartilhada.
Falhas anteriores ao commit revertem o conjunto; mudanças de estado usam locks
na ordem agendamento, comanda.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.agendamento import Agendamento, AgendamentoServico
from app.models.comanda import Comanda, ItemComanda
from app.models.servico import Servico
from app.models.cliente import Cliente
from app.models.usuario import PERFIS_PROFISSIONAIS, Usuario
from app.schemas.valores import validar_preco, validar_duracao
from app.schemas.agendamento import AgendamentoCreate, AgendamentoStatusUpdate
from app.services.errors import AgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado, SemPermissao, HorarioAgendamentoInvalido, ValoresAgendamentoInvalidos, ClienteInativo, ConflitoEstadoAgendamento
from app.services.permissoes_agendamento import (
    PERFIS_GESTAO_AGENDA, escopo_consulta, pode_operar_profissional,
)


from app.services import filiais, clientes as clientes_service
from app.services.persistencia import transacao_escrita, recarregar_confirmado


FUSO_BARBEARIA = ZoneInfo("America/Recife")


def agora_local() -> datetime:
    """Relógio substituível em testes, independente do fuso do servidor."""
    return datetime.now(FUSO_BARBEARIA)


TRANSICOES = {
    "pendente": {"aguardando", "em_atendimento", "cancelado"},
    "aguardando": {"em_atendimento", "cancelado"},
    "em_atendimento": {"concluido"},
    "concluido": set(),   # estado final
    "cancelado": set(),   # estado final
}


def criar_agendamento(dados: AgendamentoCreate, db: Session, usuario: Usuario) -> Agendamento:
    with transacao_escrita(db):
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        if not pode_operar_profissional(usuario, dados.barbeiro_id):
            raise SemPermissao("Sem permissão para criar agendamento para outro profissional")
        if usuario.perfil not in PERFIS_GESTAO_AGENDA and any(
            "preco" in item.model_fields_set for item in dados.servicos
        ):
            raise SemPermissao("Sem permissão para sobrescrever preços")
        filial = filiais.resolver_filial(db, usuario, dados.filial_id, bloquear=True)
        if dados.hora_inicio.tzinfo is not None:
            raise HorarioAgendamentoInvalido("Informe o horário local da barbearia, sem fuso no campo hora_inicio")
        inicio_local = datetime.combine(dados.data, dados.hora_inicio, tzinfo=FUSO_BARBEARIA)
        if inicio_local < agora_local():
            raise HorarioAgendamentoInvalido("Não é permitido criar agendamentos comuns no passado")
        profissional = db.query(Usuario).filter(
            Usuario.id == dados.barbeiro_id,
            Usuario.ativo.is_(True),
            Usuario.perfil.in_(PERFIS_PROFISSIONAIS),
        ).first()
        if not profissional:
            raise RecursoNaoEncontrado("Profissional ativo não encontrado")
        filiais.validar_profissional(db, dados.barbeiro_id, filial.id)
        if not dados.servicos:
            raise AgendamentoInvalido("Informe pelo menos um serviço")

        cliente = db.query(Cliente).populate_existing().with_for_update(read=True).filter(Cliente.id == dados.cliente_id).first()
        if not cliente:
            raise RecursoNaoEncontrado("Cliente não encontrado")
        if not cliente.ativo:
            raise ClienteInativo("Cliente inativo não pode receber novos agendamentos")

        # monta os itens, usando o padrão do serviço quando o front não manda valor
        itens = []
        itens_comanda = []
        for s in dados.servicos:
            servico = db.query(Servico).filter(Servico.id == s.servico_id, Servico.ativo == True).first()
            if not servico:
                raise RecursoNaoEncontrado("Serviço não encontrado")
            try:
                preco = validar_preco(s.preco if s.preco is not None else servico.preco)
                duracao = validar_duracao(s.tempo_estimado if s.tempo_estimado is not None else servico.tempo_estimado)
            except ValueError as exc:
                raise ValoresAgendamentoInvalidos(str(exc)) from exc
            itens.append(AgendamentoServico(
                servico_id=servico.id,
                preco=preco,
                tempo_estimado=duracao,
            ))
            itens_comanda.append(ItemComanda(
                tipo="servico",
                servico_id=servico.id,
                descricao=servico.nome,
                quantidade=1,
                preco_unitario=itens[-1].preco,
            ))
        # calcula o horário de fim
        total_min = sum(i.tempo_estimado for i in itens)
        try:
            validar_duracao(total_min)
        except ValueError as exc:
            raise ValoresAgendamentoInvalidos("Duração total deve estar entre 1 e 480 minutos") from exc
        inicio = datetime.combine(dados.data, dados.hora_inicio)
        try:
            fim = inicio + timedelta(minutes=total_min)
        except OverflowError as exc:
            raise HorarioAgendamentoInvalido("Término fora dos limites de data suportados") from exc
        if fim.date() != inicio.date():
            raise HorarioAgendamentoInvalido("Agendamento deve terminar antes da meia-noite do mesmo dia")
        hora_fim = fim.time()
        try:
            valor_total = validar_preco(sum((i.preco for i in itens), Decimal("0.00")))
        except ValueError as exc:
            raise ValoresAgendamentoInvalidos("Total da comanda excede o limite NUMERIC(10,2)") from exc

        # impede dois agendamentos sobrepostos para o mesmo barbeiro
        conflito = db.query(Agendamento).filter(
            Agendamento.barbeiro_id == dados.barbeiro_id,
            Agendamento.data == dados.data,
            Agendamento.status != "cancelado",
            Agendamento.hora_inicio < hora_fim,
            Agendamento.hora_fim > dados.hora_inicio,
        ).first()
        if conflito:
            raise HorarioOcupado("Barbeiro já tem agendamento nesse horário")

        agendamento = Agendamento(
            filial_id=filial.id,
            cliente_id=dados.cliente_id,
            barbeiro_id=dados.barbeiro_id,
            data=dados.data,
            hora_inicio=dados.hora_inicio,
            hora_fim=hora_fim,
            status="pendente",
            origem="recepcao",
            observacoes=dados.observacoes,
            criado_por=usuario.id,
            servicos=itens,
        )
        db.add(agendamento)
        db.flush()  # gera o id do agendamento sem finalizar a transação
        clientes_service.garantir_vinculo(db, dados.cliente_id, filial.id)

        comanda = Comanda(
            filial_id=filial.id,
            agendamento_id=agendamento.id,
            cliente_id=dados.cliente_id,
            barbeiro_id=dados.barbeiro_id,
            valor_total=valor_total,
            status="pendente",
            itens=itens_comanda,
        )
        db.add(comanda)
    recarregar_confirmado(db, agendamento)
    return agendamento


def atualizar_status(
    agendamento_id: UUID, dados: AgendamentoStatusUpdate, db: Session, usuario: Usuario,
    filial_id: UUID | None = None,
) -> Agendamento:
    with transacao_escrita(db):
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        try:
            filial_informada = filial_id
            filial_id = filiais.filial_do_registro(db, usuario, Agendamento, agendamento_id, escrita=True)
            if filial_informada is not None and filial_informada != filial_id:
                raise RecursoNaoEncontrado("Agendamento não encontrado")
            filiais.resolver_filial(db, usuario, filial_id, bloquear=True)
        except (SemPermissao, RecursoNaoEncontrado):
            raise RecursoNaoEncontrado("Agendamento não encontrado") from None
        # populate_existing relê inclusive entidades já presentes na identity map.
        # Todos os avanços e cancelamentos usam a mesma ordem de locks.
        agendamento = db.query(Agendamento).populate_existing().with_for_update().filter(
            Agendamento.id == agendamento_id, Agendamento.filial_id == filial_id,
        ).first()
        if not agendamento:
            raise RecursoNaoEncontrado("Agendamento não encontrado")
        if not pode_operar_profissional(usuario, agendamento.barbeiro_id):
            raise RecursoNaoEncontrado("Agendamento não encontrado")
        if dados.status == agendamento.status:
            raise AgendamentoInvalido(f"O agendamento já está '{agendamento.status}'")
        if agendamento.status == "em_atendimento" and dados.status == "cancelado":
            raise ConflitoEstadoAgendamento("Atendimento iniciado não pode ser cancelado pelo fluxo comum")
        if agendamento.status not in TRANSICOES:
            raise ConflitoEstadoAgendamento("Estado do agendamento incompatível com a operação")
        if dados.status not in TRANSICOES[agendamento.status]:
            raise AgendamentoInvalido(
                f"Não é possível mudar de '{agendamento.status}' para '{dados.status}'",
            )
        comanda = db.query(Comanda).populate_existing().with_for_update().filter(
            Comanda.agendamento_id == agendamento.id,
        ).first()
        if not comanda:
            raise ConflitoEstadoAgendamento("Agendamento sem comanda vinculada")
        esperado = {"pendente": "pendente", "aguardando": "aberta", "em_atendimento": "aberta"}
        if (comanda.filial_id, comanda.cliente_id, comanda.barbeiro_id) != (agendamento.filial_id, agendamento.cliente_id, agendamento.barbeiro_id):
            raise ConflitoEstadoAgendamento("Comanda incompatível com o agendamento")
        if comanda.status != esperado[agendamento.status]:
            raise ConflitoEstadoAgendamento("Estado da comanda incompatível com o agendamento")

        agora = datetime.now(timezone.utc)
        agendamento.status = dados.status
        if dados.status == "cancelado":
            comanda.status = "cancelada"
            agendamento.cancelado_em = agora
            agendamento.cancelado_por = usuario.id
            agendamento.motivo_cancelamento = dados.motivo_cancelamento
        elif dados.status in ("aguardando", "em_atendimento") and comanda.status == "pendente":
            comanda.status = "aberta"
            comanda.data_abertura = agora
        elif dados.status == "concluido":
            comanda.status = "fechada"
            comanda.data_fechamento = agora

    recarregar_confirmado(db, agendamento)
    return agendamento


def listar_agenda(data: date, barbeiro_id: UUID | None, db: Session, usuario: Usuario, filial_id: UUID | None = None):
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    profissional_id = escopo_consulta(usuario, barbeiro_id)
    query = db.query(Agendamento).filter(
        Agendamento.filial_id == filial.id, Agendamento.data == data, Agendamento.status != "cancelado",
    )
    if profissional_id is not None:
        query = query.filter(Agendamento.barbeiro_id == profissional_id)
    return query.order_by(Agendamento.hora_inicio).all()


def buscar_agendamento(agendamento_id, db, usuario, filial_id=None):
    usuario = filiais.usuario_atual(db, usuario)
    query = db.query(Agendamento).filter(
        Agendamento.id == agendamento_id, *filiais.filtro_acesso(usuario, Agendamento),
    )
    if filial_id is not None:
        query = query.filter(Agendamento.filial_id == filial_id)
    registro = query.first()
    if registro is None:
        raise RecursoNaoEncontrado("Agendamento não encontrado")
    return registro
