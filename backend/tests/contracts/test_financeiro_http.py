"""Contrato HTTP real sem banco/rede; falhas e DTOs dos serviços simulados."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest


def request(app, path, method='GET', payload=None, token=None, key=None):
    async def run():
        parsed = urlsplit(path)
        messages, delivered = [], False
        headers = [(b'content-type', b'application/json')]
        if token is not None:
            headers.append((b'authorization', f'Bearer {token}'.encode()))
        if key is not None:
            headers.append((b'idempotency-key', str(key).encode()))
        async def receive():
            nonlocal delivered
            if delivered:
                await asyncio.Event().wait()
            delivered = True
            return {'type': 'http.request', 'body': json.dumps(payload).encode() if payload is not None else b'', 'more_body': False}
        async def send(message):
            messages.append(message)
        await asyncio.wait_for(app({'type': 'http', 'asgi': {'version': '3.0'},
            'http_version': '1.1', 'scheme': 'http', 'method': method, 'path': parsed.path,
            'raw_path': parsed.path.encode(), 'query_string': parsed.query.encode(), 'root_path': '',
            'headers': headers, 'server': ('test', 80), 'client': ('test', 1)}, receive, send), 10)
        status = next(m['status'] for m in messages if m['type'] == 'http.response.start')
        body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
        return status, json.loads(body)
    return asyncio.run(run())


@pytest.fixture
def api(isolated_runtime):
    from app.core.security import criar_token
    from app.db.database import get_db
    from app.services import financeiro
    app = importlib.import_module('app.main').app
    db = MagicMock()
    user = SimpleNamespace(id=uuid4(), ativo=True, perfil='recepcao')
    db.get.return_value = user
    app.dependency_overrides[get_db] = lambda: db
    s = SimpleNamespace(app=app, db=db, user=user, token=criar_token(user.id),
                        service=financeiro, comanda=uuid4(), filial=uuid4())
    s.path = lambda suffix: f'/comandas/{s.comanda}/{suffix}'
    yield s
    app.dependency_overrides.clear()


def payload():
    return dict(valor='10.00', forma='pix', recebido_em='2026-11-13T10:00:00-03:00')


@pytest.mark.parametrize('suffix', ['financeiro', 'pagamentos', 'estornos', 'fechamento-financeiro'])
@pytest.mark.parametrize('token', [None, 'invalido'])
def test_nao_autenticado_401(api, suffix, token):
    assert request(api.app, api.path(suffix), 'GET' if suffix == 'financeiro' else 'POST',
                   payload(), token, uuid4())[0] == 401


@pytest.mark.parametrize('changes', [
    {'valor': 10.01}, {'valor': 10}, {'valor': True}, {'valor': None}, {'valor': '0'},
    {'valor': '-1'}, {'valor': '0.001'}, {'valor': '100000000.00'}, {'valor': 'NaN'},
    {'valor': 'Infinity'}, {'valor': '1e1'}, {'valor': '1,00'}, {'forma': 'boleto'},
    {'recebido_em': '2026-11-13T10:00:00'}, {'recebido_em': '2026-11-13'},
    {'recebido_em': 1794574800}, {'recebido_em': '2026-11-13T10:00:00.1234567Z'},
    {'recebido_em': '2026-13-13T10:00:00Z'}, {'recebido_em': None},
    {'saldo': '0.00'}, {'filial_id': str(uuid4())}, {'registrado_por': str(uuid4())},
    {'registrado_em': '2026-11-13T13:00:00Z'}, {'fingerprint': 'x'},
    {'chave_idempotencia': str(uuid4())},
])
def test_validacao_pagamento_sem_chamar_servico(api, monkeypatch, changes):
    mock = MagicMock()
    monkeypatch.setattr(api.service, 'registrar_pagamento', mock)
    status, body = request(api.app, api.path('pagamentos'), 'POST', payload() | changes, api.token, uuid4())
    assert status == 422 and isinstance(body['detail'], list)
    mock.assert_not_called()


@pytest.mark.parametrize('suffix,body', [
    ('pagamentos', payload()),
    ('estornos', {'pagamento_id': str(uuid4()), 'valor': '1', 'motivo': 'Correção', 'efetivado_em': '2026-11-13T13:00:00Z'}),
    ('fechamento-financeiro', {}),
])
@pytest.mark.parametrize('key', [None, 'invalida'])
def test_header_obrigatorio_uuid(api, suffix, body, key):
    assert request(api.app, api.path(suffix), 'POST', body, api.token, key)[0] == 422


@pytest.mark.parametrize('suffix,body', [
    ('estornos', {'pagamento_id': 'invalido', 'valor': '1', 'motivo': 'Correção', 'efetivado_em': '2026-11-13T13:00:00Z'}),
    ('estornos', {'pagamento_id': str(uuid4()), 'valor': '1', 'motivo': '  ', 'efetivado_em': '2026-11-13T13:00:00Z'}),
    ('estornos', {'pagamento_id': str(uuid4()), 'valor': 1, 'motivo': 'Correção', 'efetivado_em': '2026-11-13T13:00:00Z'}),
    ('estornos', {'pagamento_id': str(uuid4()), 'valor': '1', 'motivo': 'Correção', 'efetivado_em': '2026-11-13T13:00:00'}),
    ('estornos', {'pagamento_id': str(uuid4()), 'valor': '1', 'efetivado_em': '2026-11-13T13:00:00Z'}),
    ('fechamento-financeiro', {'motivo': '  '}), ('fechamento-financeiro', {'total': '0'}),
])
def test_validacao_estorno_e_fechamento(api, suffix, body):
    assert request(api.app, api.path(suffix), 'POST', body, api.token, uuid4())[0] == 422


@pytest.mark.parametrize('suffix,service', [
    ('financeiro', 'consultar_situacao'), ('pagamentos', 'registrar_pagamento'),
    ('estornos', 'registrar_estorno'), ('fechamento-financeiro', 'fechar_comanda'),
])
def test_delegacao_dtos_serializacao_sem_commit_http(api, monkeypatch, suffix, service):
    from app.services.financeiro import (
        ResumoFinanceiro, PagamentoRegistrado, EstornoRegistrado, FechamentoRegistrado,
    )
    key, pagamento = uuid4(), uuid4()
    instant = datetime(2026, 11, 13, 10, tzinfo=timezone(timedelta(hours=-3)))
    common = dict(comanda_id=api.comanda, filial_id=api.filial)
    audit = dict(registrado_em=instant, registrado_por=api.user.id, chave_idempotencia=key)
    bodies = {'financeiro': None, 'pagamentos': payload(),
        'estornos': dict(pagamento_id=str(pagamento), valor='10.00', motivo='  Correção  ', efetivado_em=instant.isoformat()),
        'fechamento-financeiro': {}}
    dtos = {
        'financeiro': ResumoFinanceiro(**common, situacao='aberto', total=Decimal('30.50'),
            pagamentos=Decimal('10'), estornos=Decimal('0'), recebido_liquido=Decimal('10'), saldo=Decimal('20.50')),
        'pagamentos': PagamentoRegistrado(**common, **audit, id=pagamento, valor=Decimal('10'), forma='pix', recebido_em=instant),
        'estornos': EstornoRegistrado(**common, **audit, id=uuid4(), pagamento_id=pagamento,
            valor=Decimal('10'), motivo='Correção', efetivado_em=instant),
        'fechamento-financeiro': FechamentoRegistrado(**common, **audit, total=Decimal('30.50'),
            recebido_liquido=Decimal('30.50'), motivo=None),
    }
    mock = MagicMock(return_value=dtos[suffix])
    monkeypatch.setattr(api.service, service, mock)
    status, body = request(api.app, api.path(suffix) + f'?filial_id={api.filial}',
        'GET' if suffix == 'financeiro' else 'POST', bodies[suffix], api.token, key)
    assert status == 200 and body['comanda_id'] == str(api.comanda)
    if suffix == 'financeiro':
        assert body['saldo'] == '20.50'
        mock.assert_called_once_with(api.comanda, api.db, api.user, api.filial)
    else:
        args = mock.call_args
        assert args.args == (api.comanda,)
        assert args.kwargs['db'] is api.db and args.kwargs['usuario'] is api.user
        assert args.kwargs['filial_id'] == api.filial and args.kwargs['chave_idempotencia'] == key
        assert body['registrado_em'] == '2026-11-13T13:00:00Z'
        assert 'fingerprint' not in body
        if suffix != 'fechamento-financeiro':
            assert isinstance(args.kwargs['valor'], Decimal) and body['valor'] == '10.00'
        if suffix == 'estornos':
            assert args.kwargs['motivo'] == 'Correção'
    api.db.commit.assert_not_called()
    api.db.begin.assert_not_called()
    api.db.rollback.assert_not_called()


@pytest.mark.parametrize('error,status,code', [
    ('EntradaFinanceiraInvalida', 422, 'entrada_financeira_invalida'),
    ('AcessoFinanceiroNegado', 403, 'acesso_financeiro_negado'),
    ('ComandaFinanceiraNaoEncontrada', 404, 'comanda_financeira_nao_encontrada'),
    ('HistoricoFinanceiroNaoVerificado', 409, 'historico_financeiro_nao_verificado'),
    ('EstadoFinanceiroIncompativel', 409, 'estado_financeiro_incompativel'),
    ('SaldoInsuficiente', 409, 'saldo_insuficiente'),
    ('LimiteEstornoExcedido', 409, 'limite_estorno_excedido'),
    ('ConflitoIdempotenciaFinanceira', 409, 'conflito_idempotencia'),
    ('DadosFinanceirosInconsistentes', 500, 'dados_financeiros_inconsistentes'),
    ('ConflitoPersistencia', 409, 'conflito_persistencia'),
    ('TransacaoAbortada', 503, 'transacao_abortada'),
    ('ConfirmacaoIndeterminada', 503, 'confirmacao_indeterminada'),
    ('BancoIndisponivel', 503, 'banco_indisponivel'),
    ('FalhaPersistencia', 500, 'falha_persistencia'),
])
def test_erros_estaveis_sanitizados(api, monkeypatch, error, status, code):
    from app.services import financeiro_errors, persistencia
    cls = getattr(financeiro_errors, error, None) or getattr(persistencia, error)
    monkeypatch.setattr(api.service, 'registrar_pagamento', MagicMock(side_effect=cls('SQL senha-secreta interna')))
    response = request(api.app, api.path('pagamentos'), 'POST', payload(), api.token, uuid4())
    assert response[0] == status and response[1]['detail']['codigo'] == code
    assert 'senha-secreta' not in json.dumps(response)


@pytest.mark.parametrize('dependencia', [False, True])
def test_sqlalchemy_cru_sanitizado_inclusive_autenticacao(api, monkeypatch, dependencia):
    from sqlalchemy.exc import ProgrammingError
    erro = ProgrammingError('SQL senha-secreta', {}, Exception('credencial interna'))
    if dependencia:
        api.db.get.side_effect = erro
    else:
        monkeypatch.setattr(api.service, 'consultar_situacao', MagicMock(side_effect=erro))
    status, body = request(api.app, api.path('financeiro'), token=api.token)
    assert status == 500 and body['detail']['codigo'] == 'falha_persistencia'
    assert 'senha-secreta' not in json.dumps(body) and 'credencial interna' not in json.dumps(body)


def test_openapi_financeiro_com_headers_decimal_timezone_e_erros(api):
    status, schema = request(api.app, '/openapi.json')
    assert status == 200
    for suffix in ('financeiro', 'pagamentos', 'estornos', 'fechamento-financeiro'):
        method = 'get' if suffix == 'financeiro' else 'post'
        operation = schema['paths'][f'/comandas/{{comanda_id}}/{suffix}'][method]
        assert operation['security'] == [{'OAuth2PasswordBearer': []}]
        assert {'200', '401', '403', '404', '409', '422', '500', '503'} <= operation['responses'].keys()
        if method == 'post':
            key = next(p for p in operation['parameters'] if p['name'] == 'Idempotency-Key')
            assert key['required'] and key['in'] == 'header' and key['schema']['format'] == 'uuid'
    schemas = schema['components']['schemas']
    pagamento = schemas['PagamentoCreate']
    assert pagamento['additionalProperties'] is False
    assert pagamento['properties']['valor']['type'] == 'string'
    assert pagamento['properties']['recebido_em']['format'] == 'date-time'
    assert schemas['PagamentoOut']['properties']['valor']['type'] == 'string'
