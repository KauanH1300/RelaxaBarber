"""Fronteira cliente: identidade da sessao; nucleo de agenda compartilhado."""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select
from app.models import Agendamento, Comanda, Empresa, Filial, Cliente, Servico
from app.models.financeiro import PagamentoComanda
from app.models.reserva_portal import RestricaoServico
from app.schemas.agendamento import AgendamentoStatusUpdate
from app.schemas.reagendamento import ReagendamentoUpdate
from app.schemas.minha_agenda import MinhaAgendaOut
from app.services import portal_cliente as portal, agendamento as agenda, reagendamento, reserva_publica, jornada, horarios_filial
from app.services.errors import RecursoNaoEncontrado, ConflitoEstadoAgendamento, HorarioOcupado
from app.services.persistencia import transacao_escrita


def propria(db, id_, cliente_id, bloquear=False):
    q=select(Agendamento).where(Agendamento.id==id_,Agendamento.cliente_id==cliente_id).execution_options(populate_existing=True)
    if bloquear:q=q.with_for_update()
    a=db.scalar(q)
    if a is None:raise RecursoNaoEncontrado('Agendamento não encontrado')
    return a


def futura(a):
    return datetime.combine(a.data,a.hora_inicio,tzinfo=agenda.FUSO_BARBEARIA)>agenda.agora_local()


def comanda_compativel(db,a,bloquear=False):
    q=select(Comanda).where(Comanda.agendamento_id==a.id).execution_options(populate_existing=True)
    if bloquear:q=q.with_for_update()
    c=db.scalar(q)
    if not c or (c.filial_id,c.cliente_id,c.barbeiro_id)!=(a.filial_id,a.cliente_id,a.barbeiro_id):return None
    if c.status!={'pendente':'pendente','aguardando':'aberta'}.get(a.status):return None
    db.expire(c,['controle_financeiro'])
    if c.controle_financeiro is not None and c.controle_financeiro.fechamento is not None:return None
    # Client actions never settle, refund or modify a financial movement.
    if db.scalar(select(PagamentoComanda.id).where(PagamentoComanda.comanda_id==c.id).limit(1)):return None
    return c


def resposta(db,a):
    proximo=futura(a) and a.status not in ('cancelado','concluido')
    elegivel=proximo and a.status in ('pendente','aguardando') and a.filial.ativa and a.filial.empresa.ativa and comanda_compativel(db,a) is not None
    return MinhaAgendaOut(id=a.id,filial=a.filial.nome,
        servicos=[{'nome':s.servico.nome,'duracao':s.tempo_estimado,'valor':s.preco} for s in a.servicos],
        barbeiro={'id':a.barbeiro_id,'nome':a.barbeiro.nome},data=a.data,hora_inicio=a.hora_inicio,hora_fim=a.hora_fim,
        duracao=sum(s.tempo_estimado for s in a.servicos),valor=sum((s.preco for s in a.servicos),Decimal('0.00')),
        status=a.status,atualizado_em=a.atualizado_em,proximo=proximo,pode_cancelar=elegivel,pode_remarcar=elegivel)


def listar(db,token):
    perfil=portal.autenticar(db,token)
    rows=db.scalars(select(Agendamento).where(Agendamento.cliente_id==perfil.id).order_by(Agendamento.data.desc(),Agendamento.hora_inicio.desc(),Agendamento.id)).all()
    return [resposta(db,a) for a in rows]


def consultar(db,token,id_):
    perfil=portal.autenticar(db,token)
    return resposta(db,propria(db,id_,perfil.id))


def bloquear(db,token,id_,dados):
    perfil=portal.autenticar(db,token)
    original=propria(db,id_,perfil.id)
    db.scalars(select(Empresa).order_by(Empresa.id).with_for_update(read=True)).all()
    f=db.scalar(select(Filial).where(Filial.id==original.filial_id).with_for_update(read=True).execution_options(populate_existing=True))
    db.scalar(select(Cliente).where(Cliente.id==perfil.id).with_for_update(read=True).execution_options(populate_existing=True))
    portal.autenticar(db,token)
    a=propria(db,id_,perfil.id,bloquear=True)
    if not f or not f.ativa or not f.empresa.ativa or a.status not in ('pendente','aguardando') or not futura(a):
        raise ConflitoEstadoAgendamento('Este atendimento não permite alterações pelo portal. Procure a recepção.')
    if reagendamento._versao(a.atualizado_em)!=reagendamento._versao(dados.atualizado_em_esperado):
        raise ConflitoEstadoAgendamento('Agendamento alterado. Consulte os dados atuais antes de continuar.')
    if comanda_compativel(db,a,bloquear=True) is None:
        raise ConflitoEstadoAgendamento('Este atendimento precisa ser tratado pela recepção.')
    return a,perfil


def cancelar(db,token,id_,dados):
    with transacao_escrita(db):
        a,perfil=bloquear(db,token,id_,dados)
        agenda.aplicar_status(db,a,AgendamentoStatusUpdate(status='cancelado',motivo_cancelamento='Cancelamento solicitado pelo cliente no portal',confirmado=True,atualizado_em_esperado=dados.atualizado_em_esperado),registrado_por_cliente=perfil.id)
        a.atualizado_em=datetime.now(timezone.utc)
        db.flush()
        resultado=resposta(db,a)
    return resultado


def candidatos(db,a,bloquear=False,barbeiro_id=None):
    ids={s.servico_id for s in a.servicos}
    if not ids:return []
    for id_ in sorted(ids,key=str):reserva_publica.servico_ativo(db,id_,bloquear=bloquear)
    base=reserva_publica.profissionais(db,a.filial_id,sorted(ids,key=str)[0],barbeiro_id,bloquear=bloquear)
    restritos=set(db.scalars(select(RestricaoServico.barbeiro_id).where(RestricaoServico.filial_id==a.filial_id,RestricaoServico.servico_id.in_(ids))))
    return [p for p in base if p.id not in restritos]


def opcoes(db,token,id_,data=None,barbeiro_id=None):
    perfil=portal.autenticar(db,token);a=propria(db,id_,perfil.id)
    if not resposta(db,a).pode_remarcar:raise ConflitoEstadoAgendamento('Atendimento não elegível para remarcação.')
    equipe=candidatos(db,a)
    slots=set()
    if data:
        dias=horarios_filial._dias(db,a.filial_id)
        if {d.dia_semana for d in dias}!=set(range(7)):raise portal.PortalFalha(503,'O expediente da filial ainda não está configurado.')
        for p in equipe:
            if barbeiro_id is None or p.id==barbeiro_id:
                slots.update(jornada.horarios_disponiveis(db,a.filial_id,p.id,data,sum(s.tempo_estimado for s in a.servicos),ignorar_id=a.id)['horarios'])
    return {'barbeiros':[{'id':p.id,'nome':p.nome} for p in equipe],'horarios':sorted(slots),'fuso':'America/Recife'}


def remarcar(db,token,id_,dados):
    with transacao_escrita(db),db.no_autoflush:
        a,perfil=bloquear(db,token,id_,dados)
        agenda.validar_inicio(dados.data,dados.hora_inicio)
        if {d.dia_semana for d in horarios_filial._dias(db,a.filial_id)}!=set(range(7)):
            raise portal.PortalFalha(503,'O expediente da filial ainda não está configurado.')
        fim=agenda.calcular_termino(dados.data,dados.hora_inicio,sum(s.tempo_estimado for s in a.servicos))
        escolhido=None
        for p in candidatos(db,a,bloquear=True,barbeiro_id=dados.barbeiro_id):
            try:agenda.validar_disponibilidade(db,a.filial_id,p.id,dados.data,dados.hora_inicio,fim,ignorar_id=a.id)
            except (HorarioOcupado,agenda.HorarioAgendamentoInvalido):continue
            escolhido=p;break
        if escolhido is None:raise HorarioOcupado('Horário indisponível. Escolha outro horário ou profissional.')
        pedido=ReagendamentoUpdate(data=dados.data,hora_inicio=dados.hora_inicio,barbeiro_id=escolhido.id,atualizado_em_esperado=dados.atualizado_em_esperado,motivo='Remarcação solicitada pelo cliente no portal')
        reagendamento.aplicar_reagendamento(db,a,pedido,registrado_por_cliente=perfil.id)
        resultado=resposta(db,a)
    return resultado
