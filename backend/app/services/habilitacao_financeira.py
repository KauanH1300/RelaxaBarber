"""Conferencia explicita de reservas publicas; nunca concilia legado ou recebimentos."""
import json
from sqlalchemy import select
from app.models import ControleFinanceiroComanda, ItemComanda, PerfilEnum, ReservaPortal
from app.services import financeiro as f
from app.services.financeiro_errors import AcessoFinanceiroNegado, EstadoFinanceiroIncompativel
from app.services.regras_financeiras import fingerprint, identificador, motivo_auditavel


def conferir(db, agendamento, comanda):
    if agendamento is None:
        raise EstadoFinanceiroIncompativel('Comanda avulsa não é reserva pública')
    if (agendamento.origem != 'portal_cliente' or agendamento.criado_por is not None
        or agendamento.status not in ('pendente', 'aguardando', 'em_atendimento', 'concluido')
        or comanda.status not in ('pendente', 'aberta') or comanda.data_fechamento is not None):
        raise EstadoFinanceiroIncompativel('Somente comandas abertas de reservas publicas podem ser habilitadas')
    reserva = db.scalar(select(ReservaPortal).where(ReservaPortal.agendamento_id == agendamento.id,
                                                    ReservaPortal.cliente_id == comanda.cliente_id))
    if reserva is None:
        raise EstadoFinanceiroIncompativel('Origem publica nao comprovada')
    itens = list(db.scalars(select(ItemComanda).where(ItemComanda.comanda_id == comanda.id, ItemComanda.ativo.is_(True))
                          .order_by(ItemComanda.id).execution_options(populate_existing=True)))
    total = f._total(db, comanda)
    if not itens or comanda.valor_total != total or any(i.tipo != 'servico' or not i.servico_id or not i.descricao.strip() for i in itens):
        raise EstadoFinanceiroIncompativel('Itens e valores exigem revisao especifica')
    payload = dict(comanda=str(comanda.id), filial=str(comanda.filial_id), cliente=str(comanda.cliente_id),
        barbeiro=str(comanda.barbeiro_id), agendamento=str(agendamento.id), origem=agendamento.origem,
        status=comanda.status, atendimento=agendamento.status, total=format(total, '.2f'),
        itens=[dict(id=str(i.id), servico=str(i.servico_id), descricao=i.descricao,
                    quantidade=i.quantidade, preco=format(i.preco_unitario, '.2f')) for i in itens])
    return dict(origem='portal_cliente', conferencia=fingerprint('conferencia_portal', dados=json.dumps(payload, sort_keys=True)),
                total=total, itens=payload['itens'], situacao=agendamento.status)


def habilitar(comanda_id, *, conferencia, confirmado, motivo, chave_idempotencia, db, usuario, filial_id=None):
    with f._escrita(db):
        ator, agendamento, comanda = f._contexto(db, usuario, comanda_id, filial_id)
        if ator.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
            raise AcessoFinanceiroNegado('Somente ADMIN ou RECEPCAO podem habilitar')
        chave = identificador(chave_idempotencia)
        motivo = motivo_auditavel(motivo, obrigatorio=True)
        if confirmado is not True or len(motivo) > 1000:
            raise EstadoFinanceiroIncompativel('Conferencia explicita obrigatoria')
        esperado = fingerprint('habilitacao_portal', conferencia=conferencia, motivo=motivo)
        registro = f._registro(db, ControleFinanceiroComanda, comanda)
        if registro is not None:
            if registro.chave_idempotencia != chave:
                raise EstadoFinanceiroIncompativel('Comanda ja habilitada; consulte o financeiro')
            f._repeticao(registro, esperado)
        else:
            atual = conferir(db, agendamento, comanda)
            if atual['conferencia'] != conferencia:
                raise EstadoFinanceiroIncompativel('Comanda alterada; confira novamente antes de habilitar')
            registro = ControleFinanceiroComanda(comanda_id=comanda.id, filial_id=comanda.filial_id,
                registrado_por=ator.id, motivo=motivo, chave_idempotencia=chave, fingerprint=esperado)
            db.add(registro)
            db.flush()
            db.refresh(registro)
        resultado = dict(comanda_id=registro.comanda_id, filial_id=registro.filial_id,
            registrado_por=registro.registrado_por, registrado_em=registro.registrado_em,
            chave_idempotencia=registro.chave_idempotencia, motivo=registro.motivo)
    return resultado
