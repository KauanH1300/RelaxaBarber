"""Acesso publico reduzido; mesmos horarios, criacao e EXCLUDE da agenda interna."""
import hashlib
from uuid import UUID
from sqlalchemy import select, delete, text
from app.models import Empresa, Filial, Usuario, UsuarioFilial, Cliente, Servico, Agendamento
from app.models.usuario import PERFIS_PROFISSIONAIS
from app.models.reserva_portal import RestricaoServico as Restricao, ReservaPortal
from app.schemas.agendamento import AgendamentoCreate
from app.schemas.reserva_publica import ReservaPublicaOut, ProfissionalPublico
from app.services import portal_cliente as portal, agendamento, jornada, horarios_filial, filiais
from app.services.persistencia import transacao_escrita
from app.services.errors import HorarioAgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado, ValoresAgendamentoInvalidos


def listar_filiais_publicas(db):
    return list(db.scalars(select(Filial).join(Empresa).where(Filial.ativa.is_(True),
        Empresa.ativa.is_(True), Filial.agenda_publica.is_(True)).order_by(Filial.nome, Filial.id)))


def filial_publica(db, bloquear=False, exigir_expediente=True, filial_id=None):
    if bloquear:
        db.scalars(select(Empresa).order_by(Empresa.id).with_for_update(read=True)).all()
    query = select(Filial).join(Empresa).where(Filial.ativa.is_(True),Empresa.ativa.is_(True),Filial.agenda_publica.is_(True)).order_by(Filial.id)
    if filial_id is not None:
        query=query.where(Filial.id==filial_id)
    if bloquear: query=query.with_for_update(read=True,of=Filial)
    rows=list(db.scalars(query.execution_options(populate_existing=True).limit(2)))
    if len(rows)!=1: raise portal.PortalFalha(503,'Agenda online temporariamente indisponível.')
    dias=horarios_filial._dias(db,rows[0].id)
    if exigir_expediente and (len(dias)!=7 or {d.dia_semana for d in dias}!=set(range(7))):
        raise portal.PortalFalha(503,'O expediente para reservas online ainda não está configurado.')
    return rows[0]


def servico_ativo(db,id_,bloquear=False):
    q=select(Servico).where(Servico.id==id_,Servico.ativo.is_(True)).execution_options(populate_existing=True)
    if bloquear:q=q.with_for_update(read=True)
    s=db.scalar(q)
    if s is None:raise RecursoNaoEncontrado('Serviço indisponível.')
    return s


def profissionais(db,filial_id,servico_id,barbeiro_id=None,bloquear=False):
    ids = servico_id if isinstance(servico_id, (list, tuple)) else [servico_id]
    restrito=select(Restricao.servico_id).where(Restricao.barbeiro_id==Usuario.id,
        Restricao.filial_id==filial_id,Restricao.servico_id.in_(ids)).exists()
    q=select(Usuario).join(UsuarioFilial,UsuarioFilial.usuario_id==Usuario.id).where(
        Usuario.ativo.is_(True),Usuario.perfil.in_(PERFIS_PROFISSIONAIS),UsuarioFilial.ativo.is_(True),
        UsuarioFilial.filial_id==filial_id,~restrito).order_by(Usuario.id)
    if barbeiro_id:q=q.where(Usuario.id==barbeiro_id)
    # Exclusive user locks serialize automatic assignment with internal SHARE locks.
    if bloquear:q=q.with_for_update(of=Usuario)
    return list(db.scalars(q.execution_options(populate_existing=True)))


def _servicos(db, ids, bloquear=False):
    ids = ids if isinstance(ids, (list, tuple)) else [ids]
    if not ids or len(ids) > 20 or len(ids) != len(set(ids)):
        raise ValoresAgendamentoInvalidos('Escolha serviços distintos')
    return [servico_ativo(db, ident, bloquear=bloquear) for ident in sorted(ids, key=str)]


def listar_servicos(db, filial_id):
    f = filial_publica(db, exigir_expediente=False, filial_id=filial_id)
    servicos = db.scalars(select(Servico).where(Servico.ativo.is_(True)).order_by(Servico.nome)).all()
    return [dict(id=s.id, nome=s.nome, preco=s.preco, tempo_estimado=s.tempo_estimado, ativo=s.ativo)
            for s in servicos if profissionais(db, f.id, s.id)]


def listar_profissionais(db,servico_id,filial_id=None):
    f=filial_publica(db,exigir_expediente=False,filial_id=filial_id); servicos=_servicos(db,servico_id)
    return profissionais(db,f.id,[s.id for s in servicos])


def listar_horarios(db,servico_id,data,barbeiro_id=None,filial_id=None):
    f=filial_publica(db,filial_id=filial_id); servicos=_servicos(db,servico_id)
    duracao=sum(s.tempo_estimado for s in servicos)
    if not 1 <= duracao <= 480: raise ValoresAgendamentoInvalidos('Duração total inválida')
    horarios=set()
    for p in profissionais(db,f.id,[s.id for s in servicos],barbeiro_id):
        horarios.update(jornada.horarios_disponiveis(db,f.id,p.id,data,duracao)['horarios'])
    return dict(data=data,duracao=duracao,horarios=sorted(horarios),fuso='America/Recife')


def resposta(db,a):
    p=db.get(Usuario,a.barbeiro_id)
    return ReservaPublicaOut(id=a.id,status=a.status,data=a.data,hora_inicio=a.hora_inicio,hora_fim=a.hora_fim,
        barbeiro=ProfissionalPublico(id=p.id,nome=p.nome),servico=', '.join(s.servico.nome for s in a.servicos))


def confirmar(db,dados,token):
    with transacao_escrita(db):
        perfil=portal.autenticar(db,token)
        excluir = {'chave', 'filial_id', 'servicos_ids'} if dados.servicos_ids is None and dados.filial_id is None else {'chave'}
        fingerprint=hashlib.sha256(dados.model_dump_json(exclude=excluir).encode()).hexdigest()
        if db.get_bind().dialect.name=='postgresql':
            lock=int.from_bytes(hashlib.sha256(f'{perfil.id}:{dados.chave}'.encode()).digest()[:8],'big',signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:chave)'),{'chave':lock})
        anterior=db.get(ReservaPortal,(perfil.id,dados.chave),populate_existing=True)
        if anterior:
            if anterior.fingerprint!=fingerprint:raise portal.PortalFalha(409,'Pedido já utilizado com outras escolhas. Revise seu agendamento.')
            a=db.get(Agendamento,anterior.agendamento_id)
            if not a or a.cliente_id!=perfil.id:raise portal.PortalFalha(409,'Pedido indisponível.')
            return resposta(db,a)
        f=filial_publica(db,bloquear=True,filial_id=dados.filial_id)
        servicos=_servicos(db,dados.servicos_ids or [dados.servico_id],bloquear=True)
        agendamento.validar_inicio(dados.data,dados.hora_inicio)
        if dados.hora_inicio.second or dados.hora_inicio.minute%15:raise HorarioAgendamentoInvalido('Selecione um horário da lista de disponibilidade.')
        fim=agendamento.calcular_termino(dados.data,dados.hora_inicio,sum(s.tempo_estimado for s in servicos))
        candidatos=profissionais(db,f.id,[s.id for s in servicos],dados.barbeiro_id,bloquear=True)
        cliente=db.scalar(select(Cliente).where(Cliente.id==perfil.id).with_for_update(read=True).execution_options(populate_existing=True))
        portal.autenticar(db,token)  # Recheck account/session changes after locks.
        if not cliente or not cliente.ativo:raise portal.PortalFalha(401,'Entre novamente na sua conta.')
        escolhido=None
        for p in candidatos:
            filiais.validar_profissional(db,p.id,f.id)
            try:agendamento.validar_disponibilidade(db,f.id,p.id,dados.data,dados.hora_inicio,fim)
            except (HorarioOcupado,HorarioAgendamentoInvalido):continue
            escolhido=p;break
        if escolhido is None:raise HorarioOcupado('Este horário não está mais disponível. Escolha outro horário ou profissional.')
        entrada=AgendamentoCreate(cliente_id=perfil.id,filial_id=f.id,barbeiro_id=escolhido.id,data=dados.data,
            hora_inicio=dados.hora_inicio,servicos=[{'servico_id':s.id} for s in servicos])
        a=agendamento.persistir_reserva(entrada,db,f,None,origem='portal_cliente')
        db.flush()
        db.add(ReservaPortal(cliente_id=perfil.id,chave=dados.chave,fingerprint=fingerprint,agendamento_id=a.id))
        resultado=resposta(db,a)
    return resultado


def consultar(db,chave,token):
    perfil=portal.autenticar(db,token)
    pedido=db.get(ReservaPortal,(perfil.id,chave))
    if pedido is None:raise RecursoNaoEncontrado('Reserva não encontrada.')
    a=db.get(Agendamento,pedido.agendamento_id)
    if a is None or a.cliente_id!=perfil.id:raise RecursoNaoEncontrado('Reserva não encontrada.')
    return resposta(db,a)


def consultar_restricoes(db,usuario,filial_id,barbeiro_id):
    from app.models import PerfilEnum
    from app.services.errors import SemPermissao
    usuario=filiais.usuario_atual(db,usuario)
    if usuario.perfil!=PerfilEnum.ADMIN:raise SemPermissao('Sem permissão')
    filiais.resolver_filial(db,usuario,filial_id)
    filiais.validar_profissional(db,barbeiro_id,filial_id)
    return {'servicos':list(db.scalars(select(Servico).order_by(Servico.nome,Servico.id))),
        'restricoes':list(db.scalars(select(Restricao.servico_id).where(Restricao.filial_id==filial_id,Restricao.barbeiro_id==barbeiro_id)))}


def configurar_restricoes(db,usuario,filial_id,barbeiro_id,dados):
    from app.services.gestao_filiais import _filial_exclusiva
    with transacao_escrita(db):
        f=_filial_exclusiva(db,usuario,filial_id)
        filiais.resolver_filial(db,usuario,f.id,bloquear=True)
        filiais.validar_profissional(db,barbeiro_id,f.id)
        # Keep explicit restrictions even while a service is inactive.
        for id_ in sorted(set(dados.servicos),key=str):
            if db.scalar(select(Servico.id).where(Servico.id==id_).with_for_update(read=True)) is None:
                raise RecursoNaoEncontrado('Serviço não encontrado')
        db.execute(delete(Restricao).where(Restricao.filial_id==f.id,Restricao.barbeiro_id==barbeiro_id))
        db.add_all([Restricao(filial_id=f.id,barbeiro_id=barbeiro_id,servico_id=id_) for id_ in set(dados.servicos)])
    return {'restricoes':sorted(set(dados.servicos),key=str)}
