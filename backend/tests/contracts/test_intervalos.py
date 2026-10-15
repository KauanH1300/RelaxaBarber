from datetime import time
from uuid import uuid4

import pytest
from fastapi import HTTPException


def test_termino_soma_duracoes(scenario):
    appointment = scenario.create(servicos=[
        dict(servico_id=scenario.service_id, tempo_estimado=20),
        dict(servico_id=uuid4(), tempo_estimado=40),
    ])
    assert appointment.hora_inicio == time(9)
    assert appointment.hora_fim == time(10)


@pytest.mark.parametrize("start,duration", [("23:30:00", 60), ("23:30:00", 30)])
def test_nao_pode_atingir_dia_seguinte(scenario, start, duration):
    with pytest.raises(HTTPException) as exc:
        scenario.create(
            hora_inicio=start,
            servicos=[dict(servico_id=scenario.service_id, tempo_estimado=duration)],
        )
    assert exc.value.status_code == 422
    scenario.db.add.assert_not_called()


def test_data_passada_rejeitada(scenario):
    with pytest.raises(HTTPException) as exc:
        scenario.create(data="2000-01-01")
    assert exc.value.status_code == 422
    scenario.db.add.assert_not_called()
