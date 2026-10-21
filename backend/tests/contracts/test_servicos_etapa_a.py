"""Contratos de serviços: schemas e HTTP reais, somente SQLite em memória."""
import asyncio
import importlib
import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError


@pytest.fixture
def catalogo(isolated_runtime):
    return importlib.import_module('app.schemas.servico')


VALIDO = dict(nome='Corte', preco=0, tempo_estimado=30, comissao_padrao=0)


@pytest.mark.parametrize('valor', [0, '0.00', 100, '100.00', '45.25', Decimal('12.50')])
def test_comissoes_validas(catalogo, valor):
    for schema, dados in [(catalogo.ServicoCreate, VALIDO), (catalogo.ServicoUpdate, {})]:
        servico = schema(**(dados | {'comissao_padrao': valor}))
        assert servico.comissao_padrao == Decimal(str(valor))
        assert isinstance(servico.comissao_padrao, Decimal)
        assert isinstance(servico.model_dump(mode='json')['comissao_padrao'], (int, float))


@pytest.mark.parametrize('valor', [-1, '100.01', '0.001', '100.000', 'NaN', 'sNaN',
                                  'Infinity', '-Infinity', float('inf'), float('nan'),
                                  True, False, 'abc', {}, [], None])
def test_comissoes_invalidas(catalogo, valor):
    for schema, dados in [(catalogo.ServicoCreate, VALIDO), (catalogo.ServicoUpdate, {})]:
        with pytest.raises(ValidationError):
            schema(**(dados | {'comissao_padrao': valor}))


@pytest.mark.parametrize('campo', ['nome', 'comissao_padrao', 'ativo', 'preco', 'tempo_estimado'])
def test_nulos_rejeitados_e_omissao_preservada(catalogo, campo):
    with pytest.raises(ValidationError):
        catalogo.ServicoUpdate(**{campo: None})
    assert catalogo.ServicoUpdate().model_dump(exclude_unset=True) == {}
    assert catalogo.ServicoUpdate(ativo=False).model_dump(exclude_unset=True) == {'ativo': False}
    assert catalogo.ServicoUpdate(nome=' Novo ').model_dump(exclude_unset=True) == {'nome': 'Novo'}


async def requisicao(app, caminho, metodo='GET', dados=None, token=None):
    mensagens = []
    entregue = False
    body = json.dumps(dados).encode() if dados is not None else b''
    async def receive():
        nonlocal entregue
        if entregue:
            await asyncio.Event().wait()
        entregue = True
        return {'type': 'http.request', 'body': body, 'more_body': False}
    async def send(message):
        mensagens.append(message)
    headers = [(b'content-type', b'application/json')]
    if token:
        headers.append((b'authorization', f'Bearer {token}'.encode()))
    await asyncio.wait_for(app({
        'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
        'scheme': 'http', 'method': metodo, 'path': caminho, 'raw_path': caminho.encode(),
        'query_string': b'', 'root_path': '', 'headers': headers,
        'server': ('test', 80), 'client': ('test', 1),
    }, receive, send), 5)
    status = next(m['status'] for m in mensagens if m['type'] == 'http.response.start')
    raw = b''.join(m.get('body', b'') for m in mensagens if m['type'] == 'http.response.body')
    return status, json.loads(raw) if raw else None


@pytest.fixture
def http_catalogo(memory_session, models, monkeypatch):
    import fastapi.dependencies.utils
    import fastapi.routing
    from app.db.database import get_db
    from app.core.security import criar_token
    async def inline(function, *args, **kwargs):
        return function(*args, **kwargs)
    monkeypatch.setattr(fastapi.dependencies.utils, 'run_in_threadpool', inline)
    monkeypatch.setattr(fastapi.routing, 'run_in_threadpool', inline)
    app = importlib.import_module('app.main').app
    db = memory_session
    tokens = {None: None}
    for perfil in ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe']:
        user = models.Usuario(nome=perfil, email=f'{perfil}@example.com', senha_hash='ficticio', perfil=perfil)
        db.add(user)
        db.flush()
        tokens[perfil] = criar_token(user.id)
    ativo = models.Servico(**VALIDO, ativo=True)
    inativo = models.Servico(**(VALIDO | {'nome': 'Inativo'}), ativo=False)
    db.add_all([ativo, inativo])
    db.commit()
    ids = (ativo.id, inativo.id)
    anteriores = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = lambda: db
    def chamar(path, metodo='GET', dados=None, perfil=None):
        return asyncio.run(requisicao(app, path, metodo, dados, tokens[perfil]))
    yield SimpleNamespace(chamar=chamar, ativo=ids[0], inativo=ids[1], app=app, db=db)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(anteriores)


@pytest.mark.parametrize('perfil', [None, 'admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_visibilidade_listagem_e_consulta(http_catalogo, perfil):
    s = http_catalogo
    for path in ['/servicos/', f'/servicos/{s.ativo}']:
        status, data = s.chamar(path, perfil=perfil)
        assert status == 200
        if isinstance(data, list):
            assert len(data) == 1
            data = data[0]
        assert data['id'] == str(s.ativo)
        assert data['preco'] == 0
        assert data['tempo_estimado'] == 30
        assert data['ativo'] is True
        assert ('comissao_padrao' in data) == (perfil == 'admin')
        assert ('data_cadastro' in data) == (perfil == 'admin')


@pytest.mark.parametrize('perfil', [None, 'admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_inexistente_e_inativo(http_catalogo, perfil):
    s = http_catalogo
    assert s.chamar(f'/servicos/{uuid4()}', perfil=perfil)[0] == 404
    assert s.chamar(f'/servicos/{s.inativo}', perfil=perfil)[0] == (200 if perfil == 'admin' else 404)


@pytest.mark.parametrize('campo', ['nome', 'comissao_padrao', 'ativo', 'preco', 'tempo_estimado'])
def test_null_http_422_antes_de_persistir(http_catalogo, monkeypatch, campo):
    s = http_catalogo
    commit = MagicMock(side_effect=AssertionError('Não deve persistir'))
    monkeypatch.setattr(s.db, 'commit', commit)
    assert s.chamar(f'/servicos/{s.ativo}', 'PUT', {campo: None}, 'admin')[0] == 422
    commit.assert_not_called()


@pytest.mark.parametrize('valor', [-1, 101, '1.001', 'NaN', True, 'abc'])
@pytest.mark.parametrize('metodo', ['POST', 'PUT'])
def test_comissao_invalida_http_422(http_catalogo, monkeypatch, valor, metodo):
    s = http_catalogo
    commit = MagicMock(side_effect=AssertionError('Não deve persistir'))
    monkeypatch.setattr(s.db, 'commit', commit)
    path = '/servicos/' if metodo == 'POST' else f'/servicos/{s.ativo}'
    assert s.chamar(path, metodo, VALIDO | {'comissao_padrao': valor}, 'admin')[0] == 422
    commit.assert_not_called()


@pytest.mark.parametrize('perfil', [None, 'recepcao', 'barbeiro', 'barbeiro_chefe'])
@pytest.mark.parametrize('metodo', ['POST', 'PUT', 'DELETE'])
def test_escrita_restrita(http_catalogo, perfil, metodo):
    s = http_catalogo
    path = '/servicos/' if metodo == 'POST' else f'/servicos/{s.ativo}'
    assert s.chamar(path, metodo, VALIDO, perfil)[0] == (401 if perfil is None else 403)


def test_crud_admin_e_atualizacao_parcial(http_catalogo):
    s = http_catalogo
    status, novo = s.chamar('/servicos/', 'POST', VALIDO | {'comissao_padrao': '100.00'}, 'admin')
    assert status == 201 and novo['comissao_padrao'] == 100
    path = f"/servicos/{novo['id']}"
    status, editado = s.chamar(path, 'PUT', {'comissao_padrao': '0.00'}, 'admin')
    assert status == 200 and editado['comissao_padrao'] == 0
    assert editado['nome'] == VALIDO['nome'] and editado['tempo_estimado'] == 30
    assert s.chamar(path, 'DELETE', perfil='admin')[0] == 204
    assert s.chamar(path)[0] == 404
    assert s.chamar(path, perfil='admin')[1]['ativo'] is False


def test_token_invalido_nao_recebe_dados(http_catalogo):
    s = http_catalogo
    for path in ['/servicos/', f'/servicos/{s.ativo}']:
        assert asyncio.run(requisicao(s.app, path, token='invalido'))[0] == 401


@pytest.mark.parametrize('campo,valor', [
    ('preco', -1), ('preco', '0.001'), ('preco', '100000000'),
    ('tempo_estimado', 0), ('tempo_estimado', 481), ('tempo_estimado', 1.5),
    ('nome', ''), ('nome', '   '),
])
@pytest.mark.parametrize('metodo', ['POST', 'PUT'])
def test_validacoes_preservadas_http(http_catalogo, monkeypatch, campo, valor, metodo):
    s = http_catalogo
    commit = MagicMock(side_effect=AssertionError('Não deve persistir'))
    monkeypatch.setattr(s.db, 'commit', commit)
    path = '/servicos/' if metodo == 'POST' else f'/servicos/{s.ativo}'
    assert s.chamar(path, metodo, VALIDO | {campo: valor}, 'admin')[0] == 422
    commit.assert_not_called()
