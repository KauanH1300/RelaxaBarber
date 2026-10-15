from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


@pytest.fixture
def catalogo(isolated_runtime):
    from app.schemas import servico
    return servico


def item(schemas, scenario, **values):
    return schemas.ServicoAgendamentoCreate(servico_id=scenario.service_id, **values)


@pytest.mark.parametrize('price', ['-0.01', '1.001', '0.000', '999999999', '100000000.00', 'NaN', 'sNaN', 'Infinity', '-Infinity', float('nan'), float('inf'), True, 'abc'])
@pytest.mark.parametrize('context', ['agendamento', 'cadastro', 'edicao'])
def test_precos_invalidos(schemas, scenario, catalogo, price, context):
    with pytest.raises(ValidationError):
        if context == 'agendamento':
            item(schemas, scenario, preco=price)
        elif context == 'cadastro':
            catalogo.ServicoCreate(nome='Corte', preco=price, tempo_estimado=30, comissao_padrao=10)
        else:
            catalogo.ServicoUpdate(preco=price)


@pytest.mark.parametrize('price', [0, '0.00', '1.23', '99999999.99'])
def test_precos_validos_e_serializacao_numerica(schemas, scenario, catalogo, price):
    assert item(schemas, scenario, preco=price).preco == Decimal(str(price))
    data = catalogo.ServicoCreate(nome='Corte', preco=price, tempo_estimado=30, comissao_padrao=10)
    assert isinstance(data.preco, Decimal)
    assert isinstance(data.model_dump(mode='json')['preco'], (int, float))
    assert data.model_json_schema(mode='serialization')['properties']['preco']['type'] == 'number'
    assert catalogo.ServicoUpdate(preco=price).preco == data.preco


@pytest.mark.parametrize('duration', [0, -1, 481, 1.5, 30.0, True, '30', float('nan'), float('inf')])
@pytest.mark.parametrize('context', ['agendamento', 'cadastro', 'edicao'])
def test_duracoes_invalidas(schemas, scenario, catalogo, duration, context):
    with pytest.raises(ValidationError):
        if context == 'agendamento':
            item(schemas, scenario, tempo_estimado=duration)
        elif context == 'cadastro':
            catalogo.ServicoCreate(nome='Corte', preco=0, tempo_estimado=duration, comissao_padrao=10)
        else:
            catalogo.ServicoUpdate(tempo_estimado=duration)


@pytest.mark.parametrize('duration', [1, 480])
def test_limites_duracao_validos(schemas, scenario, catalogo, duration):
    assert item(schemas, scenario, tempo_estimado=duration).tempo_estimado == duration
    assert catalogo.ServicoCreate(nome='Corte', preco=0, tempo_estimado=duration, comissao_padrao=10).tempo_estimado == duration
    assert catalogo.ServicoUpdate(tempo_estimado=duration).tempo_estimado == duration


@pytest.mark.parametrize('field', ['preco', 'tempo_estimado'])
def test_edicao_rejeita_null_mas_preserva_omissao(catalogo, field):
    with pytest.raises(ValidationError):
        catalogo.ServicoUpdate(**{field: None})
    assert catalogo.ServicoUpdate().model_dump(exclude_unset=True) == {}


def test_servico_gratuito_na_resposta_catalogo(catalogo):
    data = SimpleNamespace(id=uuid4(), nome='Cortesia', preco=Decimal('0.00'),
                           tempo_estimado=1, comissao_padrao=10, ativo=True,
                           data_cadastro=datetime.now(timezone.utc), atualizado_em=None)
    output = catalogo.ServicoOut.model_validate(data).model_dump(mode='json')
    assert output['preco'] == 0.0
    assert isinstance(output['preco'], float)


@pytest.mark.parametrize('client', [None, SimpleNamespace(ativo=False)])
def test_cliente_inexistente_ou_inativo(scenario, models, client):
    scenario.db.query(models.Cliente).filter.return_value.first.return_value = client
    with pytest.raises(HTTPException) as exc:
        scenario.create()
    assert exc.value.status_code == (404 if client is None else 409)
    scenario.db.add.assert_not_called()
    scenario.db.flush.assert_not_called()
    scenario.db.commit.assert_not_called()


@pytest.mark.parametrize('field,value', [
    ('preco', Decimal('-0.01')), ('preco', Decimal('1.001')),
    ('preco', Decimal('NaN')), ('preco', Decimal('Infinity')),
    ('preco', Decimal('100000000')), ('preco', None),
    ('tempo_estimado', 0), ('tempo_estimado', 481), ('tempo_estimado', 1.5),
    ('tempo_estimado', True), ('tempo_estimado', None),
])
def test_padrao_invalido_do_servico_rejeitado_sem_gravar(scenario, field, value):
    setattr(scenario.service, field, value)
    with pytest.raises(HTTPException) as exc:
        scenario.create()
    assert exc.value.status_code == 422
    scenario.db.add.assert_not_called()
    scenario.db.commit.assert_not_called()


def test_padrao_gratuito_valido(scenario, models):
    scenario.service.preco = Decimal('0.00')
    appointment = scenario.create()
    command = next(c.args[0] for c in scenario.db.add.call_args_list if isinstance(c.args[0], models.Comanda))
    assert appointment.servicos[0].preco == command.valor_total == Decimal('0.00')


@pytest.mark.parametrize('second,allowed', [('0.01', True), ('0.02', False)])
def test_limite_total_comanda_sem_arredondamento(scenario, models, second, allowed):
    services = [dict(servico_id=scenario.service_id, preco='99999999.98', tempo_estimado=1),
                dict(servico_id=uuid4(), preco=second, tempo_estimado=1)]
    if allowed:
        scenario.create(servicos=services)
        command = next(c.args[0] for c in scenario.db.add.call_args_list if isinstance(c.args[0], models.Comanda))
        assert command.valor_total == Decimal('99999999.99')
        assert sum(i.preco_unitario * i.quantidade for i in command.itens) == command.valor_total
    else:
        with pytest.raises(HTTPException) as exc:
            scenario.create(servicos=services)
        assert exc.value.status_code == 422
        scenario.db.add.assert_not_called()
        scenario.db.flush.assert_not_called()
        scenario.db.commit.assert_not_called()


@pytest.mark.parametrize('second,allowed', [(240, True), (241, False)])
def test_limite_duracao_total(scenario, second, allowed):
    services = [dict(servico_id=scenario.service_id, tempo_estimado=240),
                dict(servico_id=uuid4(), tempo_estimado=second)]
    if allowed:
        assert scenario.create(servicos=services).hora_fim.hour == 17
    else:
        with pytest.raises(HTTPException) as exc:
            scenario.create(servicos=services)
        assert exc.value.status_code == 422
        scenario.db.add.assert_not_called()


@pytest.mark.parametrize('start,duration,allowed', [('23:58:00', 1, True), ('23:59:00', 1, False), ('23:59:00', 2, False)])
def test_limite_meia_noite(scenario, start, duration, allowed):
    values = dict(hora_inicio=start, servicos=[dict(servico_id=scenario.service_id, tempo_estimado=duration)])
    if allowed:
        assert scenario.create(**values).hora_fim.isoformat() == '23:59:00'
    else:
        with pytest.raises(HTTPException) as exc:
            scenario.create(**values)
        assert exc.value.status_code == 422
        scenario.db.add.assert_not_called()


def test_limite_final_do_calendario_controlado(scenario):
    with pytest.raises(HTTPException) as exc:
        scenario.create(data='9999-12-31', hora_inicio='23:59:00', servicos=[dict(servico_id=scenario.service_id, tempo_estimado=1)])
    assert exc.value.status_code == 422
    scenario.db.add.assert_not_called()


def test_limites_aplicacao_compativeis_com_models(models):
    from app.schemas.valores import PRECO_MAXIMO
    for column in [models.Servico.__table__.c.preco, models.AgendamentoServico.__table__.c.preco,
                   models.Comanda.__table__.c.valor_total, models.ItemComanda.__table__.c.preco_unitario]:
        assert (column.type.precision, column.type.scale) == (10, 2)
    assert PRECO_MAXIMO == Decimal('99999999.99')
