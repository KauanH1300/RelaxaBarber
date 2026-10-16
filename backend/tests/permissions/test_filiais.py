"""Política real com ORM/HTTP em memória; sem mock das autorizações."""
import asyncio
import json
from datetime import date
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import select, text


@pytest.fixture
def unidades(memory_session, models, schemas):
    from app.services.agendamento import criar_agendamento
    db = memory_session
    empresa = models.Empresa(nome='RelaxaBarber')
    a = models.Filial(nome='A', empresa=empresa)
    b = models.Filial(nome='B', empresa=empresa)
    users = {}
    for role in ('admin', 'recepcao', 'barbeiro_chefe', 'barbeiro', 'itinerante', 'outro'):
        users[role] = models.Usuario(nome=role, email=f'{role}@example.test', senha_hash='ficticio', perfil=role if role not in ('itinerante','outro') else 'barbeiro')
    client = models.Cliente(nome='Cliente global', telefone='000001')
    service = models.Servico(nome='Corte', preco=30, tempo_estimado=30, comissao_padrao=10)
    db.add_all([empresa,a,b,client,service,*users.values()])
    for role in ('recepcao','barbeiro_chefe','barbeiro','itinerante'):
        db.add(models.UsuarioFilial(usuario=users[role],filial=a))
    for role in ('itinerante','outro'):
        db.add(models.UsuarioFilial(usuario=users[role],filial=b))
    db.commit()
    def payload(role='barbeiro', filial=a, hora='09:00', **changes):
        return schemas.AgendamentoCreate(cliente_id=client.id, barbeiro_id=users[role].id,
            filial_id=filial.id if filial else None, data=date(2099,1,1), hora_inicio=hora,
            servicos=[{'servico_id':service.id}], **changes)
    bookings = {}
    for role,filial,hora in [('barbeiro',a,'09:00'),('barbeiro_chefe',a,'09:00'),('itinerante',a,'09:00'),('outro',b,'09:00'),('itinerante',b,'10:00')]:
        bookings[(role,filial.nome)] = criar_agendamento(payload(role,filial,hora),db,users['admin'])
    return SimpleNamespace(db=db,a=a,b=b,users=users,client=client,service=service,payload=payload,bookings=bookings)


@pytest.mark.parametrize('role,count', [('admin',2),('recepcao',1),('barbeiro_chefe',1),('barbeiro',1),('itinerante',2)])
def test_contexto_unico_ambiguo_e_explicitamente_negado(unidades, role, count):
    from app.services.filiais import listar_filiais,resolver_filial
    from app.services.errors import FilialObrigatoria, SemPermissao
    s=unidades; user=s.users[role]
    assert len(listar_filiais(s.db,user)) == count
    if count == 2:
        with pytest.raises(FilialObrigatoria): resolver_filial(s.db,user)
    else:
        assert resolver_filial(s.db,user).id == s.a.id
        with pytest.raises(SemPermissao): resolver_filial(s.db,user,s.b.id)
    assert resolver_filial(s.db,user,s.a.id).id == s.a.id


@pytest.mark.parametrize('role,count', [('admin',3),('recepcao',3),('barbeiro_chefe',3),('barbeiro',1)])
def test_agenda_comanda_e_profissionais_respeitam_unidade(unidades, role, count):
    from app.api.routes.agendamentos import listar_agenda
    from app.api.routes.comandas import listar_comandas
    from app.api.routes.usuarios import listar_barbeiros
    s=unidades; user=s.users[role]
    agenda=listar_agenda(date(2099,1,1),db=s.db,usuario=user,filial_id=s.a.id)
    comandas=listar_comandas(db=s.db,usuario=user,filial_id=s.a.id)
    profs=listar_barbeiros(db=s.db,usuario=user,filial_id=s.a.id)
    assert len(agenda)==len(comandas)==len(profs)==count
    assert all(a.filial_id==s.a.id for a in agenda)
    assert {c.agendamento_id for c in comandas}=={a.id for a in agenda}
    if role=='barbeiro': assert {p.id for p in profs}=={user.id}


@pytest.mark.parametrize('role', ['recepcao','barbeiro_chefe','barbeiro'])
def test_uuid_de_outra_filial_oculto(unidades, role):
    from app.api.routes.agendamentos import buscar_agendamento, atualizar_status
    from app.api.routes.comandas import buscar_comanda
    from app.models import Comanda
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s=unidades; target=s.bookings[('outro','B')]; ident=target.id
    command=s.db.scalar(select(Comanda).where(Comanda.agendamento_id==ident))
    for call in (
        lambda: buscar_agendamento(ident,s.db,s.users[role]),
        lambda: buscar_comanda(command.id,s.db,s.users[role]),
        lambda: atualizar_status(ident,AgendamentoStatusUpdate(status='cancelado'),s.db,s.users[role]),
    ):
        with pytest.raises(HTTPException) as error: call()
        assert error.value.status_code==404
    assert s.db.get(type(target),ident).status=='pendente'


@pytest.mark.parametrize('role,own,allowed', [('admin',False,True),('recepcao',False,True),('barbeiro_chefe',False,False),('barbeiro_chefe',True,True),('barbeiro',False,False),('barbeiro',True,True)])
@pytest.mark.parametrize('status', ['aguardando','cancelado'])
def test_operacao_por_profissional_e_cancelamento_auditado(unidades, role, own, allowed, status):
    from app.api.routes.agendamentos import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s=unidades; target=s.bookings[(role if own else 'itinerante','A')]
    if not allowed:
        with pytest.raises(HTTPException) as error: atualizar_status(target.id,AgendamentoStatusUpdate(status=status),s.db,s.users[role])
        assert error.value.status_code==404
        assert target.status=='pendente'
    else:
        result=atualizar_status(target.id,AgendamentoStatusUpdate(status=status),s.db,s.users[role])
        assert result.status==status and result.filial_id==s.a.id
        if status=='cancelado': assert result.cancelado_por==s.users[role].id


@pytest.mark.parametrize('role,target,allowed', [('admin','itinerante',True),('recepcao','itinerante',True),('barbeiro_chefe','itinerante',False),('barbeiro_chefe','barbeiro_chefe',True),('barbeiro','itinerante',False),('barbeiro','barbeiro',True)])
def test_criacao_exige_vinculo_profissional_e_preserva_cliente_global(unidades, role, target, allowed):
    from app.api.routes.agendamentos import criar_agendamento
    from app.models import ClienteFilial,Comanda
    s=unidades; data=s.payload(target,s.a,'12:00')
    if allowed:
        appointment=criar_agendamento(data,s.db,s.users[role])
        command=s.db.scalar(select(Comanda).where(Comanda.agendamento_id==appointment.id))
        assert appointment.filial_id==command.filial_id==s.a.id
    else:
        with pytest.raises(HTTPException) as error: criar_agendamento(data,s.db,s.users[role])
        assert error.value.status_code==403
    assert s.db.query(ClienteFilial).count()==2


def test_profissional_de_outra_unidade_e_vinculo_inativo_negados(unidades):
    from app.api.routes.agendamentos import criar_agendamento
    from app.api.routes.usuarios import listar_barbeiros
    from app.models import UsuarioFilial
    s=unidades
    with pytest.raises(HTTPException) as error: criar_agendamento(s.payload('outro',s.a,'12:00'),s.db,s.users['admin'])
    assert error.value.status_code==403
    link=s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id==s.users['itinerante'].id,UsuarioFilial.filial_id==s.a.id))
    link.ativo=False;s.db.commit()
    assert s.users['itinerante'].id not in {u.id for u in listar_barbeiros(s.db,s.users['admin'],s.a.id)}
    with pytest.raises(HTTPException): criar_agendamento(s.payload('itinerante',s.a,'12:00'),s.db,s.users['admin'])


def test_perfil_e_vinculos_relidos_apesar_de_identity_map(unidades):
    from app.services.filiais import resolver_filial
    from app.services.errors import SemPermissao
    s=unidades; user=s.users['recepcao']
    # SQL direto evita sincronização automática do objeto ORM.
    s.db.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id'),{'id':user.id.hex});s.db.commit()
    with pytest.raises(SemPermissao): resolver_filial(s.db,user,s.a.id)
    admin=s.users['admin']
    s.db.execute(text("UPDATE usuarios SET perfil='BARBEIRO' WHERE id=:id"),{'id':admin.id.hex});s.db.commit()
    with pytest.raises(SemPermissao): resolver_filial(s.db,admin,s.b.id)


async def request(app, path, token, method='GET', payload=None):
    parsed=urlsplit(path); messages=[]; delivered=False
    async def receive():
        nonlocal delivered
        if delivered: await asyncio.Event().wait()
        delivered=True
        return {'type':'http.request','body':json.dumps(payload).encode() if payload else b'', 'more_body':False}
    async def send(message): messages.append(message)
    await asyncio.wait_for(app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','scheme':'http','method':method,
        'path':parsed.path,'raw_path':parsed.path.encode(),'query_string':parsed.query.encode(),'root_path':'',
        'headers':[(b'authorization',f'Bearer {token}'.encode()),(b'content-type',b'application/json')],
        'server':('test',80),'client':('test',1)},receive,send),5)
    code=next(m['status'] for m in messages if m['type']=='http.response.start')
    body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
    return code,json.loads(body) if body else None


@pytest.fixture
def http_app(unidades, monkeypatch):
    import fastapi.routing, fastapi.dependencies.utils
    from app.api.routes import agendamentos,comandas,usuarios,clientes,filiais
    from app.db.database import get_db
    async def inline(function,*a,**kw): return function(*a,**kw)
    monkeypatch.setattr(fastapi.routing,'run_in_threadpool',inline)
    monkeypatch.setattr(fastapi.dependencies.utils,'run_in_threadpool',inline)
    app=FastAPI()
    for module in (agendamentos,comandas,usuarios,clientes,filiais): app.include_router(module.router)
    app.dependency_overrides[get_db]=lambda:unidades.db
    return app


@pytest.mark.parametrize('role', ['admin','recepcao','barbeiro_chefe','barbeiro'])
def test_desativacao_cliente_admin_no_http(http_app, unidades, role):
    from app.core.security import criar_token
    s=unidades;token=criar_token(s.users[role].id)
    code,_=asyncio.run(request(http_app,f'/clientes/{s.client.id}',token,'DELETE'))
    assert code==(204 if role=='admin' else 403)
    assert s.db.get(type(s.client),s.client.id).ativo==(role!='admin')


def test_http_contexto_ambiguo_e_revogacao_com_jwt_valido(http_app, unidades):
    from app.core.security import criar_token
    from app.models import UsuarioFilial
    s=unidades; token=criar_token(s.users['admin'].id)
    for path in ('/agendamentos?data=2099-01-01','/comandas','/usuarios/barbeiros'):
        assert asyncio.run(request(http_app,path,token))[0]==422
        assert asyncio.run(request(http_app,path+('&' if '?' in path else '?')+f'filial_id={s.a.id}',token))[0]==200
    token=criar_token(s.users['recepcao'].id)
    assert asyncio.run(request(http_app,'/agendamentos?data=2099-01-01',token))[0]==200
    link=s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id==s.users['recepcao'].id));link.ativo=False;s.db.commit()
    assert asyncio.run(request(http_app,'/agendamentos?data=2099-01-01',token))[0]==403
    assert asyncio.run(request(http_app,f"/agendamentos/{s.bookings[('barbeiro','A')].id}",token))[0]==404


@pytest.mark.parametrize('role',['admin','recepcao','barbeiro_chefe','barbeiro'])
def test_criacao_negada_em_filial_nao_autorizada(unidades,role):
    from app.api.routes.agendamentos import criar_agendamento
    s=unidades
    # Profissional válido em B: negar pelo contexto do ator, não pelo cadastro.
    if role=='admin':
        assert criar_agendamento(s.payload('outro',s.b,'12:00'),s.db,s.users[role]).filial_id==s.b.id
    else:
        with pytest.raises(HTTPException) as error: criar_agendamento(s.payload('outro',s.b,'12:00'),s.db,s.users[role])
        assert error.value.status_code==403


@pytest.mark.parametrize('target',['filial','empresa','usuario'])
def test_contexto_desativado_impede_operacao(unidades,target):
    from app.services.filiais import resolver_filial
    from app.services.errors import SemPermissao
    s=unidades;user=s.users['recepcao']
    if target=='filial': s.a.ativa=False
    elif target=='empresa': s.a.empresa.ativa=False
    else: user.ativo=False
    s.db.commit()
    with pytest.raises(SemPermissao): resolver_filial(s.db,user,s.a.id)


def test_cadastro_usuario_com_vinculos_atomicos_e_selecao_obrigatoria(unidades,monkeypatch):
    from app.api.routes import usuarios
    from app.schemas.usuario import UsuarioCreate
    from app.models import Usuario,UsuarioFilial
    from sqlalchemy import event
    from sqlalchemy.exc import IntegrityError
    from app.services.persistencia import FalhaPersistencia
    s=unidades
    monkeypatch.setattr(usuarios,'hash_senha',lambda value:'ficticio')
    base=dict(nome='Novo',email='novo@example.com',senha='senha-ficticia',perfil='barbeiro')
    with pytest.raises(HTTPException) as error: usuarios.criar_usuario(UsuarioCreate(**base),s.db,s.users['admin'])
    assert error.value.status_code==422
    def fail(connection,cursor,statement,parameters,context,executemany):
        if statement.startswith('INSERT INTO usuario_filiais '): raise IntegrityError('interno',{},Exception('falha induzida'))
    event.listen(s.db.get_bind(),'before_cursor_execute',fail)
    try:
        with pytest.raises(FalhaPersistencia): usuarios.criar_usuario(UsuarioCreate(**base,filial_ids=[s.a.id,s.b.id]),s.db,s.users['admin'])
    finally: event.remove(s.db.get_bind(),'before_cursor_execute',fail)
    assert s.db.scalar(select(Usuario).where(Usuario.email==base['email'])) is None
    user=usuarios.criar_usuario(UsuarioCreate(**base,filial_ids=[s.a.id,s.b.id,s.a.id]),s.db,s.users['admin'])
    assert s.db.query(UsuarioFilial).filter(UsuarioFilial.usuario_id==user.id).count()==2


def test_admin_revogado_nao_cadastra_usuario_nem_desativa_cliente(unidades,monkeypatch):
    from app.api.routes import usuarios,clientes
    from app.schemas.usuario import UsuarioCreate
    s=unidades;admin=s.users['admin']
    s.db.execute(text("UPDATE usuarios SET perfil='RECEPCAO' WHERE id=:id"),{'id':admin.id.hex});s.db.commit()
    for call in (
        lambda: clientes.desativar_cliente(s.client.id,s.db,admin),
        lambda: usuarios.criar_usuario(UsuarioCreate(nome='Teste',email='negado@example.com',senha='senha-ficticia',perfil='barbeiro',filial_ids=[s.a.id]),s.db,admin),
    ):
        with pytest.raises(HTTPException) as error: call()
        assert error.value.status_code==403
    assert s.client.ativo


def test_criacao_sem_filial_em_contexto_unico_e_explicitamente_ambigua(unidades):
    from app.api.routes.agendamentos import criar_agendamento
    s=unidades
    data=s.payload('barbeiro',None,'12:00')
    assert criar_agendamento(data,s.db,s.users['barbeiro']).filial_id==s.a.id
    with pytest.raises(HTTPException) as error: criar_agendamento(s.payload('itinerante',None,'13:00'),s.db,s.users['admin'])
    assert error.value.status_code==422


def test_barbeiro_nao_consulta_comanda_de_terceiro_na_mesma_filial(unidades):
    from app.api.routes.comandas import buscar_comanda
    from app.api.routes.agendamentos import buscar_agendamento
    from app.models import Comanda
    s=unidades;ident=s.bookings[('itinerante','A')].id
    command=s.db.scalar(select(Comanda).where(Comanda.agendamento_id==ident))
    for call in (lambda:buscar_comanda(command.id,s.db,s.users['barbeiro']), lambda:buscar_agendamento(ident,s.db,s.users['barbeiro'])):
        with pytest.raises(HTTPException) as error: call()
        assert error.value.status_code==404
    assert buscar_comanda(command.id,s.db,s.users['barbeiro_chefe']).id==command.id


def test_http_fluxo_completo_com_contexto_automatico(http_app,unidades):
    from app.core.security import criar_token
    from app.models import Comanda
    s=unidades;token=criar_token(s.users['recepcao'].id)
    data=s.payload('barbeiro',s.a,'14:00').model_dump(mode='json');data.pop('filial_id')
    code,created=asyncio.run(request(http_app,'/agendamentos',token,'POST',data))
    assert code==201 and created['filial_id']==str(s.a.id)
    ident=created['id']
    code,cancelled=asyncio.run(request(http_app,f'/agendamentos/{ident}/status',token,'PATCH',{'status':'cancelado','motivo_cancelamento':'Cliente solicitou'}))
    assert code==200 and cancelled['filial_id']==str(s.a.id) and cancelled['cancelado_por']==str(s.users['recepcao'].id)
    command=s.db.scalar(select(Comanda).where(Comanda.agendamento_id==UUID(ident)))
    code,result=asyncio.run(request(http_app,f'/comandas/{command.id}',token))
    assert code==200 and result['filial_id']==str(s.a.id) and result['status']=='cancelada'
    assert result['total']=='30.00' and len(result['itens'])==1


@pytest.mark.parametrize('role', ['recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_jwt_multifilial_revogacao_local_nao_revoga_outra_unidade(http_app, unidades, role):
    from app.core.security import criar_token
    from app.models import UsuarioFilial, Comanda
    from app.services.agendamento import criar_agendamento
    s = unidades
    user = s.users[role]
    s.db.add(UsuarioFilial(usuario=user, filial=s.b))
    s.db.commit()
    first = s.bookings[('barbeiro' if role == 'recepcao' else role, 'A')]
    if role == 'recepcao':
        second = s.bookings[('itinerante', 'B')]
    else:
        second = criar_agendamento(s.payload(role, s.b, '15:00'), s.db, s.users['admin'])
    command = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == first.id))
    token = criar_token(user.id)
    assert asyncio.run(request(http_app, '/agendamentos?data=2099-01-01', token))[0] == 422
    assert asyncio.run(request(http_app, f'/agendamentos/{first.id}', token))[0] == 200
    assert asyncio.run(request(http_app, f'/agendamentos/{second.id}', token))[0] == 200
    link = s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == user.id, UsuarioFilial.filial_id == s.a.id))
    link.ativo = False
    s.db.commit()
    for path in (
        f'/agendamentos?data=2099-01-01&filial_id={s.a.id}&barbeiro_id={first.barbeiro_id}',
        f'/comandas?status=pendente&filial_id={s.a.id}',
        f'/usuarios/barbeiros?filial_id={s.a.id}',
    ):
        assert asyncio.run(request(http_app, path, token))[0] == 403
    for path in (f'/agendamentos/{first.id}', f'/comandas/{command.id}'):
        assert asyncio.run(request(http_app, path, token))[0] == 404
    assert asyncio.run(request(http_app, f'/agendamentos/{first.id}/status', token, 'PATCH', {'status': 'cancelado'}))[0] == 404
    code, filiais = asyncio.run(request(http_app, '/filiais', token))
    assert code == 200 and [f['id'] for f in filiais] == [str(s.b.id)]
    assert asyncio.run(request(http_app, '/agendamentos?data=2099-01-01', token))[0] == 200
    assert asyncio.run(request(http_app, f'/agendamentos/{second.id}/status', token, 'PATCH', {'status': 'aguardando'}))[0] == 200


@pytest.mark.parametrize('role', ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_filial_inicial_unica_funciona_sem_seletor(http_app, unidades, role):
    from app.core.security import criar_token
    s = unidades
    s.b.ativa = False
    s.db.commit()
    token = criar_token(s.users[role].id)
    for path in ('/agendamentos?data=2099-01-01', '/usuarios/barbeiros', '/comandas', '/clientes', '/filiais'):
        assert asyncio.run(request(http_app, path, token))[0] == 200
    data = s.payload('barbeiro' if role in ('admin', 'recepcao') else role, s.a, '16:00').model_dump(mode='json', exclude_unset=True)
    data.pop('filial_id')
    code, appointment = asyncio.run(request(http_app, '/agendamentos', token, 'POST', data))
    assert code == 201 and appointment['filial_id'] == str(s.a.id)
