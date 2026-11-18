"""Cancelamento lógico sob os locks usuário/filial/agendamento/comanda."""
from sqlalchemy import select
from decimal import Decimal
from uuid import uuid5
from app.models import (CancelamentoComanda, ItemComanda, ControleFinanceiroComanda,
    PagamentoComanda, EstornoPagamento, FechamentoFinanceiroComanda, BeneficioComanda)
from app.schemas.cancelamento_comanda import CancelamentoComandaOut
from app.services import financeiro as f
from app.services.alteracoes_itens import gestor
from app.services.financeiro_errors import (EstadoFinanceiroIncompativel, HistoricoFinanceiroNaoVerificado,
    VersaoItensDesatualizada, ConfirmacaoAjusteNecessaria)
from app.services.regras_financeiras import fingerprint
from app.models.estoque import ProdutoEstoque, MovimentoEstoque


def validar_vazia(db, comanda):
    # O controle inicial comprova o histórico; não é um recebimento. A ausência
    # dele significa legado não verificado. Habilitação posterior é auditada.
    controle = f._registro(db, ControleFinanceiroComanda, comanda)
    if controle is None:
        raise HistoricoFinanceiroNaoVerificado('Histórico financeiro não verificado')
    if controle.chave_idempotencia is not None:
        raise EstadoFinanceiroIncompativel('Comanda possui habilitação financeira registrada')
    if db.scalar(select(ItemComanda.id).where(ItemComanda.comanda_id == comanda.id, ItemComanda.ativo.is_(True)).limit(1)):
        raise EstadoFinanceiroIncompativel('Comanda possui itens ativos')
    # Existência, nunca saldo líquido: pagamento integralmente estornado ou
    # fechamento gratuito continuam sendo movimentações e impedem cancelar.
    for modelo in (PagamentoComanda, EstornoPagamento, FechamentoFinanceiroComanda, BeneficioComanda):
        if f._registro(db, modelo, comanda) is not None:
            raise EstadoFinanceiroIncompativel('Comanda possui movimentação financeira ou benefício registrado')


def cancelar(comanda_id, dados, chave_idempotencia, db, usuario, filial_id=None):
    with f._escrita(db):
        ator, agenda, comanda = f._contexto(db, usuario, comanda_id, filial_id)
        gestor(ator)
        chave = f.identificador(chave_idempotencia)
        fp = fingerprint('cancelamento_comanda_v1', **dados.model_dump())
        anterior = f._registro(db, CancelamentoComanda, comanda)
        if anterior is not None and anterior.chave_idempotencia == chave:
            f._repeticao(anterior, fp)
            return CancelamentoComandaOut.model_validate(anterior.resultado)
        if comanda.status not in ('pendente', 'aberta') or comanda.data_fechamento is not None:
            raise EstadoFinanceiroIncompativel('Somente comandas pendentes ou abertas podem ser canceladas')
        if dados.versao != comanda.versao_itens:
            raise VersaoItensDesatualizada('Comanda alterada; consulte os dados atuais')
        if comanda.tipo == 'avulsa':
            if f._registro(db, ControleFinanceiroComanda, comanda) is None:
                raise HistoricoFinanceiroNaoVerificado('Histórico financeiro não verificado')
            for modelo in (PagamentoComanda, EstornoPagamento, FechamentoFinanceiroComanda):
                if f._registro(db, modelo, comanda) is not None:
                    raise EstadoFinanceiroIncompativel('Comanda possui histórico financeiro; trate-o antes do cancelamento')
        else:
            validar_vazia(db, comanda)
        if not dados.confirmado:
            raise ConfirmacaoAjusteNecessaria('Confirme explicitamente o cancelamento da comanda')
        resultado = CancelamentoComandaOut(comanda_id=comanda.id, filial_id=comanda.filial_id,
            registrado_por=ator.id, registrado_em=f._agora(db), motivo=dados.motivo,
            chave_idempotencia=chave, versao=comanda.versao_itens+1, status_anterior=comanda.status)
        registro = CancelamentoComanda(comanda_id=comanda.id, filial_id=comanda.filial_id,
            registrado_por=ator.id, motivo=dados.motivo, chave_idempotencia=chave,
            fingerprint=fp, resultado=resultado.model_dump(mode='json'))
        db.add(registro)
        comanda.status = 'cancelada'
        if comanda.tipo == 'avulsa':
            from app.services import comissoes
            comissoes.registrar(db, comanda, f.ZERO, 'cancelamento', ator.id, chave)
            itens = db.scalars(select(ItemComanda).where(ItemComanda.comanda_id == comanda.id,
                ItemComanda.ativo.is_(True)).order_by(ItemComanda.produto_id, ItemComanda.id).with_for_update()).all()
            for item in itens:
                if item.tipo != 'produto' or item.produto_id is None or item.filial_id != comanda.filial_id:
                    raise EstadoFinanceiroIncompativel('Item incompatível com comanda avulsa')
                produto = db.scalar(select(ProdutoEstoque).where(ProdutoEstoque.id == item.produto_id,
                    ProdutoEstoque.filial_id == comanda.filial_id).with_for_update().execution_options(populate_existing=True))
                if produto is None or produto.saldo + item.quantidade > Decimal('99999999999.999'):
                    raise EstadoFinanceiroIncompativel('Não foi possível repor o estoque')
                produto.saldo += item.quantidade
                # O estado cancelado bloqueia novas operações. Preservar as
                # linhas ativas mantém os valores e descontos históricos
                # coerentes para consulta após a reposição do estoque.
                db.add(MovimentoEstoque(produto_id=produto.id, filial_id=comanda.filial_id,
                    comanda_id=comanda.id, item_comanda_id=item.id, tipo='entrada',
                    quantidade=item.quantidade, saldo_apos=produto.saldo,
                    motivo='Cancelamento de comanda avulsa', registrado_por=ator.id,
                    chave_idempotencia=uuid5(chave, str(item.id))))
                db.flush()
        comanda.versao_itens += 1
        db.flush(); db.refresh(registro)
        return CancelamentoComandaOut.model_validate(registro.resultado)
