from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize("profile", ["admin", "recepcao"])
def test_admin_e_recepcao_podem_alterar_preco(scenario, profile):
    appointment = scenario.create(
        profile=profile,
        servicos=[dict(servico_id=scenario.service_id, preco="15.00")],
    )
    assert appointment.servicos[0].preco == Decimal("15.00")


def test_barbeiro_pode_agendar_para_si_sem_alterar_preco(scenario):
    assert scenario.create(profile="barbeiro").barbeiro_id == scenario.professional_id


@pytest.mark.pending
@pytest.mark.xfail(reason="Etapa C: barbeiro ainda pode sobrescrever preço", raises=pytest.fail.Exception)
def test_barbeiro_nao_pode_alterar_preco(scenario):
    with pytest.raises(HTTPException) as exc:
        scenario.create(
            profile="barbeiro",
            servicos=[dict(servico_id=scenario.service_id, preco="15.00")],
        )
    assert exc.value.status_code == 403
    scenario.db.add.assert_not_called()


@pytest.mark.pending
@pytest.mark.xfail(reason="Etapa C: criação ainda não restringe profissional ao solicitante", raises=pytest.fail.Exception)
def test_barbeiro_nao_pode_agendar_para_outro(scenario):
    with pytest.raises(HTTPException) as exc:
        scenario.create(profile="barbeiro", user_id=uuid4())
    assert exc.value.status_code == 403
    scenario.db.add.assert_not_called()
