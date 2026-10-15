"""Matriz de acesso com rotas reais, SQL inspecionado e sessão sem conexão."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

PROFILES = ["admin", "recepcao", "barbeiro_chefe", "barbeiro"]


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("own", [True, False])
def test_criacao_por_profissional(scenario, profile, own):
    user_id = scenario.professional_id if own else uuid4()
    if own or profile in ("admin", "recepcao"):
        assert scenario.create(profile=profile, user_id=user_id).barbeiro_id == scenario.professional_id
    else:
        with pytest.raises(HTTPException) as exc:
            scenario.create(profile=profile, user_id=user_id)
        assert exc.value.status_code == 403
        scenario.db.add.assert_not_called()
        scenario.db.commit.assert_not_called()


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("price", ["0.00", "15.00", "30.00", None])
def test_sobrescrita_inclusive_igual_padrao_e_null(scenario, profile, price):
    changes = dict(servicos=[dict(servico_id=scenario.service_id, preco=price)])
    if profile in ("admin", "recepcao"):
        scenario.create(profile=profile, **changes)
    else:
        with pytest.raises(HTTPException) as exc:
            scenario.create(profile=profile, **changes)
        assert exc.value.status_code == 403
        scenario.db.query.assert_not_called()
        scenario.db.add.assert_not_called()


@pytest.mark.parametrize("profile", PROFILES)
def test_duracao_pode_ser_sobrescrita_sem_preco(scenario, profile):
    appointment = scenario.create(
        profile=profile, servicos=[dict(servico_id=scenario.service_id, tempo_estimado=45)],
    )
    assert appointment.servicos[0].tempo_estimado == 45


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("scope", ["none", "own", "other"])
def test_escopo_consulta(routes, profile, scope):
    user = SimpleNamespace(id=uuid4(), perfil=profile)
    target = None if scope == "none" else user.id if scope == "own" else uuid4()
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = []
    if profile == "barbeiro" and scope == "other":
        with pytest.raises(HTTPException) as exc:
            routes.listar_agenda(date(2099, 1, 1), target, db=db, usuario=user)
        assert exc.value.status_code == 403
        db.query.assert_not_called()
    else:
        assert routes.listar_agenda(date(2099, 1, 1), target, db=db, usuario=user) == []
        clauses = [arg for call in query.filter.call_args_list for arg in call.args]
        values = [value for clause in clauses for value in clause.compile().params.values()]
        if profile == "barbeiro":
            assert user.id in values
        elif target is not None:
            assert target in values
        else:
            assert not any("barbeiro_id =" in str(clause) for clause in clauses)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("own", [True, False])
@pytest.mark.parametrize("new", ["aguardando", "cancelado"])
def test_status_e_cancelamento(routes, schemas, profile, own, new):
    professional = uuid4()
    user = SimpleNamespace(id=professional if own else uuid4(), perfil=profile)
    appointment = SimpleNamespace(id=uuid4(), barbeiro_id=professional, status="pendente")
    command = SimpleNamespace(status="pendente", data_abertura=None)
    db = MagicMock()
    db.query.return_value.populate_existing.return_value = db.query.return_value
    db.query.return_value.with_for_update.return_value = db.query.return_value
    db.query.return_value.filter.return_value.first.side_effect = [appointment, command]
    data = schemas.AgendamentoStatusUpdate(status=new)
    if own or profile in ("admin", "recepcao"):
        assert routes.atualizar_status(appointment.id, data, db, user) is appointment
        assert appointment.status == new
        db.commit.assert_called_once()
    else:
        with pytest.raises(HTTPException) as exc:
            routes.atualizar_status(appointment.id, data, db, user)
        assert (exc.value.status_code, exc.value.detail) == (404, "Agendamento não encontrado")
        assert appointment.status == "pendente"
        assert command.status == "pendente"
        db.commit.assert_not_called()


@pytest.mark.parametrize("profile", ["barbeiro", "barbeiro_chefe"])
def test_ambos_tipos_sao_profissionais(scenario, models, profile):
    scenario.db.query(models.Usuario).filter.return_value.first.return_value = SimpleNamespace(
        id=scenario.professional_id, perfil=profile, ativo=True,
    )
    assert scenario.create().barbeiro_id == scenario.professional_id
    args = scenario.db.query(models.Usuario).filter.call_args.args
    values = [v for clause in args for v in clause.compile().params.values()]
    assert any(set(v) == {"barbeiro", "barbeiro_chefe"} for v in values if isinstance(v, (list, tuple)))
    assert any("ativo IS true" in str(clause) for clause in args)


def test_profissional_ativo_nao_encontrado(scenario, models):
    scenario.db.query(models.Usuario).filter.return_value.first.return_value = None
    with pytest.raises(HTTPException) as exc:
        scenario.create()
    assert (exc.value.status_code, exc.value.detail) == (404, "Profissional ativo não encontrado")
    scenario.db.add.assert_not_called()


def test_perfil_desconhecido_negado(scenario):
    with pytest.raises(HTTPException) as exc:
        scenario.create(profile="desconhecido")
    assert exc.value.status_code == 403
    scenario.db.query.assert_not_called()
