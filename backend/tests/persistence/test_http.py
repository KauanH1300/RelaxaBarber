import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError, DataError, TimeoutError


class DriverFailure(Exception):
    def __init__(self, code='23505', constraint='ix_clientes_email'):
        self.pgcode = code
        self.diag = SimpleNamespace(constraint_name=constraint, schema_name='public')
        super().__init__('senha-super-secreta; SQL interno do PostgreSQL')


@pytest.fixture
def application(isolated_runtime, monkeypatch, scenario):
    import fastapi.dependencies.utils
    import fastapi.routing
    from app.api.deps import get_current_user
    from app.db.database import get_db

    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)
    monkeypatch.setattr(fastapi.dependencies.utils, 'run_in_threadpool', inline)
    monkeypatch.setattr(fastapi.routing, 'run_in_threadpool', inline)
    app = importlib.import_module('app.main').app
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=scenario.professional_id, perfil='admin')
    app.dependency_overrides[get_db] = lambda: scenario.db
    yield app
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


async def request(app, path, method='GET', payload=None):
    messages = []
    delivered = False
    body = json.dumps(payload).encode() if payload is not None else b''
    async def receive():
        nonlocal delivered
        if delivered:
            await asyncio.Event().wait()
        delivered = True
        return {'type':'http.request', 'body':body, 'more_body':False}
    async def send(message):
        messages.append(message)
    await asyncio.wait_for(app({
        'type':'http', 'asgi':{'version':'3.0'}, 'http_version':'1.1', 'scheme':'http',
        'method':method, 'path':path, 'raw_path':path.encode(), 'query_string':b'', 'root_path':'',
        'headers':[(b'content-type', b'application/json')], 'server':('test',80), 'client':('test',1),
    }, receive, send), timeout=5)
    status = next(m['status'] for m in messages if m['type']=='http.response.start')
    result = b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
    return status, result.decode()


@pytest.mark.parametrize('error,status', [
    (IntegrityError('INSERT SQL-SECRETO', {}, DriverFailure('23P01', 'ex_agendamentos_profissional_periodo')), 409),
    (IntegrityError('INSERT SQL-SECRETO', {'senha':'senha-super-secreta'}, DriverFailure()), 409),
    (IntegrityError('INSERT SQL-SECRETO', {}, DriverFailure(constraint='desconhecida')), 500),
    (IntegrityError('INSERT SQL-SECRETO', {}, DriverFailure('23514', 'check_desconhecido')), 500),
    (DataError('INSERT SQL-SECRETO', {}, DriverFailure('22003')), 500),
    (OperationalError('INSERT SQL-SECRETO', {}, DriverFailure('08006')), 503),
    (ProgrammingError('INSERT SQL-SECRETO', {}, DriverFailure('42601')), 500),
])
def test_respostas_http_sem_informacao_interna(application, scenario, schemas, error, status, caplog):
    scenario.db.flush.side_effect = error
    data = schemas.AgendamentoCreate(**scenario.payload).model_dump(mode='json')
    code, body = asyncio.run(request(application, '/agendamentos', 'POST', data))
    assert code == status
    assert set(json.loads(body)) == {'detail'}
    for secret in ['SQL-SECRETO', 'senha-super-secreta', 'PostgreSQL', 'ix_clientes_email']:
        assert secret not in body
        assert secret not in caplog.text
    scenario.db.rollback.assert_called_once()
    scenario.db.commit.assert_not_called()


def test_resultado_commit_indeterminado_explicito(application, scenario, schemas):
    scenario.db.commit.side_effect = OperationalError(None, {}, DriverFailure('08006'))
    data = schemas.AgendamentoCreate(**scenario.payload).model_dump(mode='json')
    code, body = asyncio.run(request(application, '/agendamentos', 'POST', data))
    assert code == 503
    assert 'Consulte os registros' in body
    scenario.db.rollback.assert_called_once()


def test_refresh_posterior_informa_operacao_confirmada(application, scenario, schemas):
    scenario.db.refresh.side_effect = OperationalError('SQL-SECRETO', {}, DriverFailure('08006'))
    data = schemas.AgendamentoCreate(**scenario.payload).model_dump(mode='json')
    code, body = asyncio.run(request(application, '/agendamentos', 'POST', data))
    assert code == 500
    assert 'Operação confirmada' in body
    scenario.db.commit.assert_called_once()


@pytest.mark.parametrize('error,status', [
    (OperationalError('SELECT SQL-SECRETO', {}, DriverFailure('08006')), 503),
    (ProgrammingError('SELECT SQL-SECRETO', {}, DriverFailure('42601')), 500),
    (TimeoutError('SQL-SECRETO'), 503),
])
def test_falha_consulta_tambem_sanitizada(application, scenario, error, status):
    scenario.db.query.side_effect = error
    code, body = asyncio.run(request(application, '/clientes'))
    assert code == status
    assert 'SQL-SECRETO' not in body
    scenario.db.commit.assert_not_called()


@pytest.mark.parametrize('state', ['40001', '40P01'])
def test_http_abortamento_confirmado(application, scenario, schemas, state):
    scenario.db.commit.side_effect = OperationalError('SQL-SECRETO', {}, DriverFailure(state))
    data = schemas.AgendamentoCreate(**scenario.payload).model_dump(mode='json')
    code, body = asyncio.run(request(application, '/agendamentos', 'POST', data))
    assert code == 503
    assert 'transação foi abortada' in body
    assert 'Nenhuma alteração desta operação foi confirmada' in body
    assert 'Não foi possível confirmar o resultado' not in body
    assert 'SQL-SECRETO' not in body
    assert 'senha-super-secreta' not in body
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()


@pytest.mark.parametrize('state', [None, '57014', 'XX000'])
def test_http_operational_desconhecido_conservador(application, scenario, schemas, state):
    scenario.db.commit.side_effect = OperationalError('SQL-SECRETO', {}, DriverFailure(state))
    data = schemas.AgendamentoCreate(**scenario.payload).model_dump(mode='json')
    code, body = asyncio.run(request(application, '/agendamentos', 'POST', data))
    assert code == 500
    assert 'abortada' not in body
    assert 'Não foi possível confirmar o resultado' not in body
    assert 'SQL-SECRETO' not in body
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()


@pytest.mark.parametrize('phase', ['flush', 'commit'])
def test_concorrencia_http_409_preserva_contrato(application, scenario, schemas, phase):
    getattr(scenario.db, phase).side_effect = IntegrityError(
        'SQL-SECRETO', {}, DriverFailure('23P01', 'ex_agendamentos_profissional_periodo'),
    )
    data = schemas.AgendamentoCreate(**scenario.payload).model_dump(mode='json')
    code, body = asyncio.run(request(application, '/agendamentos', 'POST', data))
    assert code == 409
    assert json.loads(body) == {'detail': 'Barbeiro já tem agendamento nesse horário'}
    scenario.db.rollback.assert_called_once()
    assert scenario.db.commit.call_count == (phase == 'commit')


@pytest.mark.parametrize('old,command_status,target,expected', [
    ('em_atendimento','aberta','cancelado',409),
    ('aguardando','fechada','cancelado',409),
    ('pendente',None,'cancelado',409),
    ('cancelado','cancelada','cancelado',400),
    ('concluido','fechada','cancelado',400),
])
def test_http_conflitos_cancelamento(application, scenario, old, command_status, target, expected):
    from uuid import uuid4
    ident=uuid4()
    appointment=SimpleNamespace(id=ident,barbeiro_id=scenario.professional_id,status=old)
    command=SimpleNamespace(status=command_status) if command_status else None
    db=scenario.db
    db.query.side_effect=None
    query=db.query.return_value
    query.populate_existing.return_value=query
    query.with_for_update.return_value=query
    query.filter.return_value=query
    query.first.side_effect=[appointment,command]
    code,body=asyncio.run(request(application,f'/agendamentos/{ident}/status','PATCH',{'status':target}))
    assert code==expected
    assert set(json.loads(body))=={'detail'}
    assert appointment.status==old
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize('profile', ['admin','recepcao','barbeiro','barbeiro_chefe'])
def test_perfil_proprio_contrato_seguro_e_aditivo(application, scenario, profile):
    from datetime import datetime, timezone
    from app.api.deps import get_current_user
    user=SimpleNamespace(id=scenario.professional_id,nome='Perfil teste',email='perfil@example.com',telefone=None,
                         perfil=profile,ativo=True,data_cadastro=datetime(2030,1,1,tzinfo=timezone.utc),senha_hash='SEGREDO-HASH')
    application.dependency_overrides[get_current_user]=lambda:user
    code,body=asyncio.run(request(application,'/auth/me'))
    assert code==200
    result=json.loads(body)
    assert set(result)=={'id','nome','email','telefone','perfil','ativo','data_cadastro'}
    assert result['perfil']==profile and result['id']==str(user.id)
    assert 'SEGREDO' not in body
    scenario.db.query.assert_not_called()
    scenario.db.commit.assert_not_called()
    assert asyncio.run(request(application,'/auth/me','PATCH',{'nome':'Não editar'}))[0]==405
