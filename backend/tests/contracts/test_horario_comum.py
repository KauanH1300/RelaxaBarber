from datetime import datetime, timedelta, timezone
import importlib

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize('profile', ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
@pytest.mark.parametrize('seconds', [-86400, -1, 0, 1, 86400])
def test_limite_de_inicio_por_perfil(scenario, monkeypatch, profile, seconds):
    service = importlib.import_module('app.services.agendamento')
    now = datetime(2030, 5, 2, 9, 0, tzinfo=service.FUSO_BARBEARIA)
    monkeypatch.setattr(service, 'agora_local', lambda: now)
    start = now + timedelta(seconds=seconds)
    params = dict(profile=profile, data=start.date(), hora_inicio=start.time())
    if seconds < 0:
        with pytest.raises(HTTPException) as exc:
            scenario.create(**params)
        assert exc.value.status_code == 422
        scenario.db.query.assert_not_called()
        scenario.db.add.assert_not_called()
        scenario.db.commit.assert_not_called()
    else:
        appointment = scenario.create(**params)
        assert appointment.hora_inicio == start.time()
        scenario.db.commit.assert_called_once()


def test_calendario_recife_quando_utc_ja_mudou_de_dia(scenario, monkeypatch):
    service = importlib.import_module('app.services.agendamento')
    now_utc = datetime(2030, 5, 3, 1, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(service, 'agora_local', lambda: now_utc)
    # Ainda são 22h do dia 2 em Recife; 22h01 permanece no futuro.
    assert scenario.create(data='2030-05-02', hora_inicio='22:01:00').data.isoformat() == '2030-05-02'


def test_relogio_usa_fuso_da_barbearia(isolated_runtime):
    service = importlib.import_module('app.services.agendamento')
    assert service.agora_local().tzinfo.key == 'America/Recife'


def test_horario_com_offset_nao_causa_comparacao_ambigua(scenario):
    with pytest.raises(HTTPException) as exc:
        scenario.create(hora_inicio='09:00:00+03:00')
    assert exc.value.status_code == 422
    scenario.db.add.assert_not_called()
