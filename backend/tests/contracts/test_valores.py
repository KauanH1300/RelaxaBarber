from decimal import Decimal

import pytest
from pydantic import ValidationError


@pytest.mark.parametrize("price", [Decimal("0.00"), Decimal("12.50")])
def test_preco_nao_negativo_no_agendamento(schemas, scenario, price):
    item = schemas.ServicoAgendamentoCreate(servico_id=scenario.service_id, preco=price)
    assert item.preco == price


def test_valores_padrao_e_comanda_preservados(scenario, models):
    appointment = scenario.create()
    assert appointment.servicos[0].preco == Decimal("30.00")
    assert appointment.servicos[0].tempo_estimado == 30
    added = [call.args[0] for call in scenario.db.add.call_args_list]
    command = next(obj for obj in added if isinstance(obj, models.Comanda))
    assert command.valor_total == Decimal("30.00")
    assert command.itens[0].preco_unitario == Decimal("30.00")
    scenario.db.commit.assert_called_once()


@pytest.mark.pending
@pytest.mark.xfail(reason="Etapa D: preço sobrescrito negativo ainda é aceito", raises=pytest.fail.Exception)
def test_preco_negativo_rejeitado(schemas, scenario):
    try:
        schemas.ServicoAgendamentoCreate(servico_id=scenario.service_id, preco="-0.01")
    except ValidationError:
        return
    pytest.fail("Preço negativo foi aceito")


@pytest.mark.parametrize("duration", [0, -1])
@pytest.mark.pending
@pytest.mark.xfail(reason="Etapa D: falta limite positivo da duração", raises=pytest.fail.Exception)
def test_duracao_nao_positiva_rejeitada(schemas, scenario, duration):
    with pytest.raises(ValidationError):
        schemas.ServicoAgendamentoCreate(
            servico_id=scenario.service_id, tempo_estimado=duration,
        )


def test_duracao_fracionaria_rejeitada(schemas, scenario):
    with pytest.raises(ValidationError):
        schemas.ServicoAgendamentoCreate(
            servico_id=scenario.service_id, tempo_estimado=1.5,
        )


@pytest.mark.pending
@pytest.mark.xfail(reason="Etapa D: catálogo ainda exige preço maior que zero", raises=ValidationError)
def test_catalogo_aceita_servico_gratuito(isolated_runtime):
    from app.schemas.servico import ServicoCreate

    service = ServicoCreate(nome="Cortesia", preco=0, tempo_estimado=10, comissao_padrao=10)
    assert service.preco == 0
