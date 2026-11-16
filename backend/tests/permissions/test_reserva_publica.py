import asyncio
from datetime import date,time,timedelta
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import urlsplit
import pytest
from sqlalchemy import select,event
from test_portal_clientes import portal,ativar,cadastro,logar,request  # noqa:F401


@pytest.fixture
def reserva(portal,monkeypatch):
    from app.models import Empresa,Filial,Usuario,UsuarioFilial,Servico,FilialHorario,PerfilEnum
    from app.models.reserva_portal import HabilitacaoServico
    p=portal;ativar(p);p.token=logar(p,cadastro());db=p.db
    e=Empresa(nome='Teste');db.add(e);db.flush();f=Filial(nome='Barbearia',empresa_id=e.id);db.add(f);db.flush()
    s=Servico(nome='Corte',preco=30,tempo_estimado=30,comissao_padrao=10)
    a=Usuario(nome='Profissional',email='prof@example.com',senha_hash='ficticio',perfil=PerfilEnum.BARBEIRO)
    b=Usuario(nome='Outro',email='outro@example.com',senha_hash='ficticio',perfil=PerfilEnum.BARBEIRO)
    admin=Usuario(nome='Admin',email='admin@example.com',senha_hash='ficticio',perfil=PerfilEnum.ADMIN)
    db.add_all([s,a,b,admin]);db.flush()
    db.add_all([UsuarioFilial(usuario_id=u.id,filial_id=f.id) for u in [a,b]])
    db.add_all([FilialHorario(filial_id=f.id,dia_semana=d,fechado=False,hora_inicio=time(8),hora_fim=time(18)) for d in range(7)])
    db.flush();db.add(HabilitacaoServico(filial_id=f.id,barbeiro_id=a.id,servico_id=s.id));db.commit()
    p.f,p.s,p.a,p.b,p.admin=f,s,a,b,admin
    monkeypatch.delenv('PUBLIC_BOOKING_FILIAL_ID',raising=False)
    return p


def api(p,path,body=None,method='GET',cookie='auto',**kwargs):
    async def app(scope,receive,send):
        parts=urlsplit(scope['path']);scope['path']=parts.path;scope['query_string']=parts.query.encode()
        await p.app(scope,receive,send)
    return asyncio.run(request(app,path,body,method=method,cookie=p.token if cookie=='auto' else cookie,**kwargs))


def dados(p,**changes):
    return dict(servico_id=str(p.s.id),barbeiro_id=str(p.a.id),data='2099-05-20',hora_inicio='09:00',chave=str(uuid4()))|changes


def test_catalogos_publicos_nao_expoem_dados_internos(reserva):
    p=reserva
    status,rows,_=api(p,f'/publico/barbeiros?servico_id={p.s.id}',cookie=None)
    assert status==200 and rows==[{'id':str(p.a.id),'nome':p.a.nome}]
    status,slots,_=api(p,f'/publico/horarios?servico_id={p.s.id}&data=2099-05-20',cookie=None)
    assert status==200 and slots['fuso']=='America/Recife' and '09:00' in slots['horarios']
    assert set(slots)=={'data','duracao','fuso','horarios'} and slots['horarios'][-1]=='17:30'


def test_reserva_sessao_snapshots_comanda_e_idempotencia(reserva):
    from app.models import Agendamento,Comanda,ControleFinanceiroComanda,ClienteFilial
    p=reserva;body=dados(p)
    code,out,_=api(p,'/portal-clientes/reservas',body,'POST');assert code==201
    assert set(out)=={'id','status','data','hora_inicio','hora_fim','barbeiro','servico','fuso'}
    a=p.db.scalar(select(Agendamento));c=p.db.scalar(select(Comanda))
    assert a.cliente_id==c.cliente_id and a.origem=='portal_cliente' and a.criado_por is None
    assert c.agendamento_id==a.id and c.valor_total==30 and len(a.servicos)==len(c.itens)==1
    assert p.db.query(ControleFinanceiroComanda).count()==0 and p.db.query(ClienteFilial).count()==1
    assert api(p,'/portal-clientes/reservas',body,'POST')[1]['id']==out['id']
    assert p.db.query(Agendamento).count()==1
    assert api(p,'/portal-clientes/reservas',body|{'hora_inicio':'10:00'},'POST')[0]==409
    assert api(p,'/portal-clientes/reservas/'+body['chave'])[1]['id']==out['id']


@pytest.mark.parametrize('field,value',[('cliente_id',str(uuid4())),('filial_id',str(uuid4())),('preco',1),('tempo_estimado',1),('criado_por',str(uuid4()))])
def test_nao_aceita_identidade_ou_valores_controlados_pelo_cliente(reserva,field,value):
    p=reserva;assert api(p,'/portal-clientes/reservas',dados(p)|{field:value},'POST')[0]==422


def test_auth_csrf_e_sessao_revogada(reserva):
    from app.core.security import criar_token
    from app.services import portal_cliente
    p=reserva;body=dados(p)
    assert api(p,'/portal-clientes/reservas',body,'POST',cookie=None)[0]==401
    assert api(p,'/portal-clientes/reservas',body,'POST',cookie=criar_token(p.admin.id))[0]==401
    assert api(p,'/portal-clientes/reservas',body,'POST',origin='https://hostil.example')[0]==403
    portal_cliente.logout(p.db,p.token)
    assert api(p,'/portal-clientes/reservas',body,'POST')[0]==401


@pytest.mark.parametrize('caso',['inativo','sem_habilitacao','vinculo_inativo','folga','intervalo','excecao','fora_expediente','passado','servico_inativo'])
def test_revalida_regras_na_confirmacao(reserva,caso):
    from app.models import UsuarioFilial,JornadaBarbeiro
    from app.schemas.jornada import JornadaUpdate
    p=reserva;body=dados(p)
    if caso=='inativo':p.a.ativo=False
    if caso=='sem_habilitacao':body['barbeiro_id']=str(p.b.id)
    if caso=='vinculo_inativo':p.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id==p.a.id)).ativo=False
    if caso=='fora_expediente':body['hora_inicio']='18:00'
    if caso=='passado':body['data']='2000-01-01'
    if caso=='servico_inativo':p.s.ativo=False
    if caso in ('folga','intervalo','excecao'):
        dias=[dict(dia_semana=d,fechado=caso=='folga',**({} if caso=='folga' else {'hora_inicio':'08:00','hora_fim':'18:00','intervalos':[{'dia_semana':d,'fechado':False,'hora_inicio':'09:00','hora_fim':'10:00'}] if caso=='intervalo' else []})) for d in range(7)]
        config=JornadaUpdate(dias=dias,excecoes=[{'data':'2099-05-20','dia_semana':date(2099,5,20).weekday(),'fechado':True}] if caso=='excecao' else [])
        p.db.add(JornadaBarbeiro(filial_id=p.f.id,barbeiro_id=p.a.id,configuracao=config.model_dump(mode='json')))
    p.db.commit()
    assert api(p,'/portal-clientes/reservas',body,'POST')[0] in (409,422,404)


def test_ocupado_e_cancelado_nao_bloqueia_novo(reserva):
    from app.models import Agendamento
    p=reserva
    assert api(p,'/portal-clientes/reservas',dados(p),'POST')[0]==201
    assert api(p,'/portal-clientes/reservas',dados(p),'POST')[0]==409
    p.db.scalar(select(Agendamento)).status='cancelado';p.db.commit()
    assert api(p,'/portal-clientes/reservas',dados(p),'POST')[0]==201


def test_sem_preferencia_atribui_outro_habilitado(reserva):
    from app.models.reserva_portal import HabilitacaoServico
    p=reserva
    assert api(p,'/portal-clientes/reservas',dados(p),'POST')[0]==201
    p.db.add(HabilitacaoServico(filial_id=p.f.id,barbeiro_id=p.b.id,servico_id=p.s.id));p.db.commit()
    code,result,_=api(p,'/portal-clientes/reservas',dados(p,barbeiro_id=None),'POST')
    assert code==201 and result['barbeiro']['id']==str(p.b.id)


def test_configuracao_fechada_e_admin_habilitacoes(reserva):
    from app.models import FilialHorario
    from app.services import reserva_publica as s
    from app.schemas.reserva_publica import HabilitacoesUpdate
    from app.services.errors import SemPermissao
    p=reserva
    with pytest.raises(SemPermissao):s.configurar_habilitacoes(p.db,p.a,p.f.id,p.a.id,HabilitacoesUpdate(servicos=[]))
    s.configurar_habilitacoes(p.db,p.admin,p.f.id,p.a.id,HabilitacoesUpdate(servicos=[]))
    assert api(p,f'/publico/barbeiros?servico_id={p.s.id}')[1]==[]
    p.db.query(FilialHorario).delete();p.db.commit()
    assert api(p,f'/publico/barbeiros?servico_id={p.s.id}')[0]==503


def test_rollback_nao_deixa_agendamento_comanda_ou_pedido(reserva):
    from app.models import Agendamento,Comanda
    from app.models.reserva_portal import ReservaPortal
    from app.services.reserva_publica import confirmar
    from app.schemas.reserva_publica import ReservaPublicaCreate
    p=reserva
    def falhar(session):raise RuntimeError('falha injetada')
    event.listen(p.db,'before_commit',falhar)
    try:
        with pytest.raises(RuntimeError):confirmar(p.db,ReservaPublicaCreate(**dados(p)),p.token)
    finally:event.remove(p.db,'before_commit',falhar)
    p.db.rollback()
    assert all(p.db.query(model).count()==0 for model in (Agendamento,Comanda,ReservaPortal))


def test_reserva_de_outro_cliente_nao_pode_ser_consultada(reserva):
    p=reserva;body=dados(p)
    assert api(p,'/portal-clientes/reservas',body,'POST')[0]==201
    outra=cadastro(email='outra@example.com',telefone='21988881234')
    ativar(p,email=outra['email'],telefone=outra['telefone'])
    outro_token=logar(p,outra)
    assert api(p,'/portal-clientes/reservas/'+body['chave'],cookie=outro_token)[0]==404
    assert api(p,'/portal-clientes/reservas/'+body['chave'],cookie=None)[0]==401


def test_disponibilidade_observa_horario_local_recife(reserva,monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app.services import agendamento
    p=reserva
    monkeypatch.setattr(agendamento,'agora_local',lambda:datetime(2099,5,20,9,1,tzinfo=ZoneInfo('America/Recife')))
    code,out,_=api(p,f'/publico/horarios?servico_id={p.s.id}&data=2099-05-20')
    assert code==200 and out['horarios'][0]=='09:15' and '09:00' not in out['horarios']
    assert api(p,'/portal-clientes/reservas',dados(p),'POST')[0]==422
