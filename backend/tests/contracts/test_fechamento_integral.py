"""Confirmação explícita, Decimal e contrato HTTP integral sem banco externo."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from test_financeiro_http import api, request, payload


def parcela():
    return dict(valor=Decimal('10.00'), forma='pix', recebido_em=datetime(2026,1,1,tzinfo=timezone.utc), confirmado=True)


@pytest.mark.parametrize('mudanca', [
    {'valor':10.0}, {'valor':'10.00'}, {'valor':Decimal('0')}, {'valor':Decimal('-1')},
    {'valor':Decimal('NaN')}, {'valor':Decimal('Infinity')}, {'valor':Decimal('0.001')},
    {'valor':Decimal('100000000')}, {'forma':'fiado'}, {'confirmado':False},
    {'confirmado':1}, {'confirmado':'true'}, {'confirmado':None},
    {'recebido_em':datetime(2026,1,1)}, {'saldo':Decimal('0')},
])
def test_servico_revalida_entrada_sem_confiar_no_http(isolated_runtime, mudanca):
    from app.services.financeiro import _confirmados
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with pytest.raises(EntradaFinanceiraInvalida):
        _confirmados([parcela() | mudanca])


@pytest.mark.parametrize('entrada', [None, {}, 'pix', [parcela()]*17, [{}]])
def test_servico_rejeita_lista_invalida(isolated_runtime, entrada):
    from app.services.financeiro import _confirmados
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with pytest.raises(EntradaFinanceiraInvalida):
        _confirmados(entrada)


def test_decimal_confirmacao_e_limite_no_schema(isolated_runtime):
    from app.schemas.financeiro import FechamentoFinanceiroCreate
    from pydantic import ValidationError
    p = dict(valor='10.00', forma='pix', recebido_em='2026-01-01T10:00:00-03:00', confirmado=True)
    dados = FechamentoFinanceiroCreate(pagamentos=[p]).model_dump()
    assert dados['pagamentos'][0]['valor'] == Decimal('10.00')
    assert dados['pagamentos'][0]['confirmado'] is True
    assert FechamentoFinanceiroCreate().pagamentos == []
    for invalido in [False, None, 1, 'true']:
        with pytest.raises(ValidationError):
            FechamentoFinanceiroCreate(pagamentos=[p | {'confirmado':invalido}])
    with pytest.raises(ValidationError):
        FechamentoFinanceiroCreate(pagamentos=[{k:v for k,v in p.items() if k!='confirmado'}])


def test_http_delega_lista_decimal_e_preserva_resposta(api, monkeypatch):
    from uuid import uuid4
    from unittest.mock import MagicMock
    from app.services.financeiro import FechamentoRegistrado
    chave = uuid4()
    mock = MagicMock(return_value=FechamentoRegistrado(api.comanda, api.filial,
        Decimal('30.50'), Decimal('30.50'), None, datetime.now(timezone.utc), api.user.id, chave))
    monkeypatch.setattr(api.service, 'fechar_comanda', mock)
    body = {'pagamentos':[payload() | {'confirmado':True},
                          payload() | {'valor':'20.50', 'forma':'credito', 'confirmado':True}]}
    status, resposta = request(api.app, api.path('fechamento-financeiro'), 'POST', body, api.token, chave)
    assert status == 200 and resposta['total'] == resposta['recebido_liquido'] == '30.50'
    argumentos = mock.call_args.kwargs
    assert argumentos['chave_idempotencia'] == chave
    assert [p['valor'] for p in argumentos['pagamentos']] == [Decimal('10.00'),Decimal('20.50')]
    assert all(p['confirmado'] is True for p in argumentos['pagamentos'])
    api.db.commit.assert_not_called()


def test_openapi_identifica_contrato_e_depreca_avulso(api):
    schema = request(api.app, '/openapi.json')[1]
    assert schema['paths']['/comandas/{comanda_id}/pagamentos']['post']['deprecated'] is True
    entrada = schema['components']['schemas']['FechamentoFinanceiroCreate']['properties']['pagamentos']
    assert entrada['maxItems'] == 16
    pagamento = schema['components']['schemas']['PagamentoConfirmadoCreate']
    assert 'confirmado' in pagamento['required']
    assert pagamento['properties']['confirmado']['const'] is True
