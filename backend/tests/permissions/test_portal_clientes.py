"""Fluxos reais em SQLite em memória; SMTP capturado apenas nesta suíte."""
import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select


@pytest.fixture
def portal(memory_session, monkeypatch):
    import fastapi.routing, fastapi.dependencies.utils
    from app.main import app
    from app.db.database import get_db
    from app.services import entrega_codigo_cliente as entrega
    async def inline(function, *args, **kwargs): return function(*args, **kwargs)
    monkeypatch.setattr(fastapi.routing, 'run_in_threadpool', inline)
    monkeypatch.setattr(fastapi.dependencies.utils, 'run_in_threadpool', inline)
    monkeypatch.setenv('CLIENT_PORTAL_COOKIE_SECURE', 'true')
    cartas = []
    monkeypatch.setattr(entrega, 'configuracao', lambda: True)
    monkeypatch.setattr(entrega, 'enviar', lambda email, codigo: cartas.append((email,codigo)))
    app.dependency_overrides[get_db] = lambda: memory_session
    yield SimpleNamespace(app=app, db=memory_session, cartas=cartas)
    app.dependency_overrides.clear()


async def request(app, path, body=None, method='POST', cookie=None, token=None, origin='http://127.0.0.1:5173', ip='127.0.0.1'):
    messages, delivered = [], False
    async def receive():
        nonlocal delivered
        if delivered: await asyncio.Event().wait()
        delivered = True
        return {'type':'http.request', 'body':json.dumps(body).encode() if body is not None else b'', 'more_body':False}
    async def send(message): messages.append(message)
    headers = [(b'content-type', b'application/json')]
    if origin: headers.append((b'origin',origin.encode()))
    if cookie: headers.append((b'cookie',('rb_cliente_sessao='+cookie).encode()))
    if token: headers.append((b'authorization',('Bearer '+token).encode()))
    await asyncio.wait_for(app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'https','method':method,
        'path':path,'raw_path':path.encode(),'query_string':b'','root_path':'','headers':headers,
        'server':('test',443),'client':(ip,1000)},receive,send),10)
    response = next(m for m in messages if m['type']=='http.response.start')
    raw=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
    return response['status'], json.loads(raw) if raw else None, dict(response['headers'])


def call(p, endpoint, body=None, **kwargs):
    return asyncio.run(request(p.app,'/portal-clientes/'+endpoint,body,**kwargs))


def cadastro(**changes):
    return dict(nome='Cliente Portal',email='cliente@example.com',telefone='(11) 99999-1234',senha='Senha-ficticia-longa-123') | changes


def ativar(p, **changes):
    body=cadastro(**changes)
    code, result, _=call(p,'cadastro',body)
    assert code==202
    pedido=dict(solicitacao_id=result['solicitacao_id'], codigo=p.cartas[-1][1])
    assert call(p,'ativar',pedido)[0]==200
    return body,pedido


def logar(p, body):
    code,result,headers=call(p,'login',{'email':body['email'],'senha':body['senha']})
    assert code==200 and 'access_token' not in result
    cookie=headers[b'set-cookie'].decode()
    assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie and 'Path=/portal-clientes' in cookie
    return cookie.split(';')[0].split('=',1)[1]


def test_cadastro_ativacao_login_logout(portal):
    from app.models import Cliente, ContaPortalCliente, DesafioPortalCliente
    p=portal
    code,result,_=call(p,'cadastro',cadastro())
    assert code==202 and p.db.query(Cliente).count()==0
    assert call(p,'login',{'email':cadastro()['email'],'senha':cadastro()['senha']})[0]==401
    desafio=p.db.get(DesafioPortalCliente,UUID(result['solicitacao_id']))
    assert desafio.codigo_hash!=p.cartas[-1][1] and cadastro()['senha'] not in json.dumps(desafio.dados)
    assert desafio.dados['senha_hash'].startswith('$argon2')
    pedido=dict(solicitacao_id=result['solicitacao_id'],codigo=p.cartas[-1][1])
    assert call(p,'ativar',pedido)[0]==200
    assert call(p,'ativar',pedido)[0]==400
    assert p.db.query(Cliente).count()==p.db.query(ContaPortalCliente).count()==1
    cliente=p.db.scalar(select(Cliente)); assert cliente.conta_ativada and cliente.senha_hash.startswith('$argon2')
    token=logar(p,cadastro())
    code,me,_=call(p,'me',method='GET',cookie=token)
    assert code==200 and me['id']==str(cliente.id) and set(me)=={'id','nome','email','telefone'}
    assert call(p,'logout',cookie=token)[0]==204
    assert call(p,'me',method='GET',cookie=token)[0]==401


def test_cria_conta_separada_do_cliente_da_recepcao(portal):
    from app.models import Cliente
    p=portal
    cliente=Cliente(nome='Nome da recepção',email='CLIENTE@example.com',telefone='11 99999-1234')
    p.db.add(cliente);p.db.commit();id_=cliente.id
    ativar(p)
    p.db.refresh(cliente)
    assert p.db.query(Cliente).count()==2 and cliente.id==id_ and not cliente.conta_ativada
    assert cliente.nome=='Nome da recepção' and cliente.telefone=='11 99999-1234' and cliente.email=='CLIENTE@example.com'
    token = logar(p,cadastro())
    from app.services.portal_cliente import autenticar
    assert autenticar(p.db, token).id != id_


@pytest.mark.parametrize('caso',['email_divergente','telefone_divergente','sem_email','duas_pessoas','desativado'])
def test_dados_pessoais_nao_permitem_assumir_cadastro(portal,caso):
    from app.models import Cliente
    p=portal
    cliente=Cliente(nome='Cliente antigo',email='cliente@example.com',telefone='11999991234',ativo=caso!='desativado')
    if caso=='email_divergente': cliente.email='titular@example.com'
    if caso=='telefone_divergente': cliente.telefone='21988881234'
    if caso=='sem_email': cliente.email=None
    p.db.add(cliente)
    if caso=='duas_pessoas':
        cliente.telefone='21988881234'
        p.db.add(Cliente(nome='Outra pessoa',email='outra@example.com',telefone='11999991234'))
    p.db.commit();antes=p.db.query(Cliente).count()
    code,result,_=call(p,'cadastro',cadastro())
    assert code==202
    assert call(p,'ativar',dict(solicitacao_id=result['solicitacao_id'],codigo=p.cartas[-1][1]))[0]==200
    p.db.refresh(cliente)
    assert not cliente.conta_ativada and cliente.senha_hash is None and p.db.query(Cliente).count()==antes+1


def test_edicao_do_contato_durante_ativacao_nao_anexa_a_conta(portal):
    from app.models import Cliente
    p=portal;c=Cliente(nome='Antigo',email='cliente@example.com',telefone='11999991234');p.db.add(c);p.db.commit()
    _,r,_=call(p,'cadastro',cadastro());c.email='novo@example.com';p.db.commit()
    assert call(p,'ativar',dict(solicitacao_id=r['solicitacao_id'],codigo=p.cartas[-1][1]))[0]==200
    p.db.refresh(c);assert not c.conta_ativada


def test_tentativas_persistem_e_codigo_expira(portal,monkeypatch):
    from app.services import portal_cliente as service
    from app.models import DesafioPortalCliente
    p=portal;_,r,_=call(p,'cadastro',cadastro());codigo=p.cartas[-1][1]
    errado='000000' if codigo!='000000' else '999999'
    for _ in range(5): assert call(p,'ativar',dict(solicitacao_id=r['solicitacao_id'],codigo=errado))[0]==400
    d=p.db.get(DesafioPortalCliente,UUID(r['solicitacao_id']));assert d.tentativas==5 and d.consumido and d.dados is None
    assert call(p,'ativar',dict(solicitacao_id=r['solicitacao_id'],codigo=codigo))[0]==400
    now=service.agora();monkeypatch.setattr(service,'agora',lambda:now+timedelta(minutes=2))
    _,r,_=call(p,'cadastro',cadastro());codigo=p.cartas[-1][1]
    monkeypatch.setattr(service,'agora',lambda:now+timedelta(minutes=13))
    assert call(p,'ativar',dict(solicitacao_id=r['solicitacao_id'],codigo=codigo))[0]==400


def test_recuperacao_generica_redefine_e_revoga_sessoes(portal,monkeypatch):
    from app.services import portal_cliente as service
    p=portal;body,_=ativar(p);token=logar(p,body)
    now=service.agora();monkeypatch.setattr(service,'agora',lambda:now+timedelta(minutes=2))
    _,known,_=call(p,'recuperar',{'email':body['email']})
    codigo=p.cartas[-1][1]
    code,unknown,_=call(p,'recuperar',{'email':'inexistente@example.com'})
    assert code==202 and known['mensagem']==unknown['mensagem'] and set(known)==set(unknown)
    assert call(p,'ativar',dict(solicitacao_id=known['solicitacao_id'],codigo=codigo))[0]==400
    pedido=dict(solicitacao_id=known['solicitacao_id'],codigo=codigo,senha='Outra-senha-ficticia-123')
    assert call(p,'redefinir',pedido)[0]==200
    assert call(p,'redefinir',pedido)[0]==400
    assert call(p,'me',method='GET',cookie=token)[0]==401
    assert call(p,'login',dict(email=body['email'],senha=body['senha']))[0]==401
    assert logar(p,body|{'senha':pedido['senha']})


def test_smtp_ausente_ou_falhando_nao_finge_envio(portal,monkeypatch):
    from app.services import entrega_codigo_cliente as entrega
    from app.models import DesafioPortalCliente,Cliente
    p=portal
    def falhar(*args):raise entrega.EntregaIndisponivel()
    monkeypatch.setattr(entrega,'configuracao',falhar)
    assert call(p,'cadastro',cadastro())[0]==503 and p.db.query(DesafioPortalCliente).count()==0
    monkeypatch.setattr(entrega,'configuracao',lambda:True);monkeypatch.setattr(entrega,'enviar',falhar)
    assert call(p,'cadastro',cadastro())[0]==503
    d=p.db.scalar(select(DesafioPortalCliente));assert d.consumido and d.dados is None
    assert p.db.query(Cliente).count()==0


def test_limites_por_email_ip_e_login(portal):
    p=portal
    respostas=[call(p,'recuperar',{'email':'semconta@example.com'}) for _ in range(8)]
    assert all(r[0]==202 for r in respostas) and len(p.cartas)==1
    assert len({r[1]['solicitacao_id'] for r in respostas})==8
    for n in range(12): call(p,'recuperar',{'email':f'pessoa{n}@example.com'})
    assert len(p.cartas)<=10
    respostas=[call(p,'login',dict(email='semconta@example.com',senha='invalida'))[0] for _ in range(11)]
    assert respostas[:10]==[401]*10 and respostas[-1]==429


def test_isolamento_tokens_contas_e_csrf(portal):
    from app.core.security import criar_token,ler_token
    from app.models import Usuario
    p=portal;body,_=ativar(p);token=logar(p,body)
    assert ler_token(token) is None
    assert asyncio.run(request(p.app,'/auth/me',method='GET',token=token))[0]==401
    funcionario = Usuario(nome='Recepção de teste', email='recepcao@example.com',
                          senha_hash='ficticio', perfil='recepcao')
    p.db.add(funcionario)
    p.db.flush()
    staff = criar_token(funcionario.id)
    assert call(p,'me',method='GET',cookie=staff)[0]==401
    assert call(p,'me',method='GET',token=staff)[0]==401
    assert call(p,'login',dict(email=body['email'],senha=body['senha']),origin='https://invasor.example')[0]==403
    assert call(p,'logout',cookie=token,origin=None)[0]==403
    assert call(p,'me',method='GET',cookie=token)[0]==200
    assert call(p,'me/'+str(uuid4()),method='GET',cookie=token)[0]==404
    code,result,_=call(p,'cadastro',cadastro(cliente_id=str(uuid4())))
    assert code==422 and 'senha' not in json.dumps(result).lower()


def test_sessao_expirada_inativo_e_email_alterado(portal,monkeypatch):
    from app.models import Cliente
    from app.services import portal_cliente as service
    p=portal;body,_=ativar(p);token=logar(p,body);c=p.db.scalar(select(Cliente))
    c.ativo=False;p.db.commit();assert call(p,'me',method='GET',cookie=token)[0]==401
    c.ativo=True;c.email='alterado@example.com';p.db.commit();assert call(p,'me',method='GET',cookie=token)[0]==401
    c.email=body['email'];p.db.commit()
    now=service.agora();monkeypatch.setattr(service,'agora',lambda:now+timedelta(hours=9))
    assert call(p,'me',method='GET',cookie=token)[0]==401
