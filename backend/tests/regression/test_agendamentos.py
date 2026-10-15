"""Caracterização do comportamento anterior à extração, inclusive limitações."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException


@pytest.mark.parametrize("case,code,message", [
    ("empty", 400, "Informe pelo menos um serviço"),
    ("service", 404, "Serviço não encontrado"),
    ("conflict", 409, "Barbeiro já tem agendamento nesse horário"),
])
def test_erros_criacao(routes, models, scenario, case, code, message):
    if case == "service":
        scenario.db.query(models.Servico).filter.return_value.first.return_value = None
    if case == "conflict":
        scenario.db.query(models.Agendamento).filter.return_value.first.return_value = object()
    with pytest.raises(HTTPException) as exc:
        scenario.create(**({"servicos": []} if case == "empty" else {}))
    assert (exc.value.status_code, exc.value.detail) == (code, message)
    scenario.db.add.assert_not_called()
    scenario.db.commit.assert_not_called()


STATES = ["pendente", "aguardando", "em_atendimento", "concluido", "cancelado"]
ALLOWED = {
    "pendente": {"aguardando", "em_atendimento", "cancelado"},
    "aguardando": {"em_atendimento", "cancelado"},
    "em_atendimento": {"concluido"},
    "concluido": set(), "cancelado": set(),
}


@pytest.fixture
def status_scenario(routes, schemas):
    appointment = SimpleNamespace(id=uuid4(), barbeiro_id=uuid4(), status="pendente")
    command = SimpleNamespace(status="pendente", data_abertura=None, data_fechamento=None)
    db = MagicMock()
    db.query.return_value.populate_existing.return_value = db.query.return_value
    db.query.return_value.with_for_update.return_value = db.query.return_value
    db.query.return_value.filter.return_value.first.side_effect = lambda: next(results)

    def update(old, new, command_status="auto", missing=False):
        nonlocal results
        appointment.status = old
        command.status = ("aberta" if old in ("aguardando", "em_atendimento") else "pendente") if command_status == "auto" else command_status
        results = iter([None if missing else appointment, command if command_status else None])
        return routes.atualizar_status(
            appointment.id, schemas.AgendamentoStatusUpdate(status=new),
            db=db, usuario=SimpleNamespace(id=uuid4(), perfil="admin"),
        )

    results = iter(())
    return SimpleNamespace(update=update, appointment=appointment, command=command, db=db)


@pytest.mark.parametrize("old", STATES)
@pytest.mark.parametrize("new", STATES)
def test_matriz_transicoes(status_scenario, old, new):
    s = status_scenario
    if new in ALLOWED[old]:
        assert s.update(old, new) is s.appointment
        assert s.appointment.status == new
        s.db.commit.assert_called_once()
        s.db.refresh.assert_called_once_with(s.appointment)
    else:
        with pytest.raises(HTTPException) as exc:
            s.update(old, new)
        expected = (f"O agendamento já está '{old}'" if old == new else
                    f"Não é possível mudar de '{old}' para '{new}'")
        if old == "em_atendimento" and new == "cancelado":
            assert exc.value.status_code == 409
        else:
            assert (exc.value.status_code, exc.value.detail) == (400, expected)
        assert s.appointment.status == old
        s.db.commit.assert_not_called()


def test_status_agendamento_inexistente(status_scenario):
    with pytest.raises(HTTPException) as exc:
        status_scenario.update("pendente", "aguardando", missing=True)
    assert (exc.value.status_code, exc.value.detail) == (404, "Agendamento não encontrado")
    status_scenario.db.commit.assert_not_called()


@pytest.mark.parametrize("old,new,command_old,command_new", [
    ("pendente", "aguardando", "pendente", "aberta"),
    ("pendente", "em_atendimento", "pendente", "aberta"),
    ("aguardando", "em_atendimento", "aberta", "aberta"),
    ("em_atendimento", "concluido", "aberta", "fechada"),
    ("pendente", "cancelado", "pendente", "cancelada"),
    ("aguardando", "cancelado", "aberta", "cancelada"),
])
def test_efeitos_comanda(status_scenario, old, new, command_old, command_new):
    s = status_scenario
    s.update(old, new, command_old)
    assert s.command.status == command_new
    if command_old == "pendente" and command_new == "aberta":
        assert s.command.data_abertura.utcoffset().total_seconds() == 0
    if command_new == "fechada":
        assert s.command.data_fechamento.utcoffset().total_seconds() == 0
    if new == "cancelado":
        assert s.command.data_fechamento is None
    s.db.commit.assert_called_once()


def test_comanda_ausente_bloqueia_operacao(status_scenario):
    s = status_scenario
    with pytest.raises(HTTPException) as exc:
        s.update("em_atendimento", "concluido", command_status=None)
    assert exc.value.status_code == 409
    assert s.appointment.status == "em_atendimento"
    s.db.commit.assert_not_called()


def test_listagem_preserva_filtros(routes):
    db = MagicMock()
    query = db.query.return_value
    query.filter.return_value = query
    query.order_by.return_value = query
    expected = [object()]
    query.all.return_value = expected
    from datetime import date
    professional = uuid4()
    result = routes.listar_agenda(date(2099, 1, 1), professional, db=db, usuario=SimpleNamespace(id=uuid4(), perfil="admin"))
    assert result is expected
    clauses = [str(arg) for call in query.filter.call_args_list for arg in call.args]
    assert len(clauses) == 3
    assert any("agendamentos.data =" in clause for clause in clauses)
    assert any("agendamentos.status !=" in clause for clause in clauses)
    assert any("agendamentos.barbeiro_id =" in clause for clause in clauses)


def test_contrato_openapi(routes):
    app = FastAPI()
    app.include_router(routes.router)
    paths = app.openapi()["paths"]
    assert set(paths) == {"/agendamentos", "/agendamentos/{agendamento_id}/status"}
    for path, method, code in [
        ("/agendamentos", "post", "201"),
        ("/agendamentos", "get", "200"),
        ("/agendamentos/{agendamento_id}/status", "patch", "200"),
    ]:
        operation = paths[path][method]
        assert code in operation["responses"]
        assert "422" in operation["responses"]
        assert operation["security"] == [{"OAuth2PasswordBearer": []}]
        schema = operation["responses"][code]["content"]["application/json"]["schema"]
        if method == "get":
            assert schema["items"]["$ref"].endswith("/AgendamentoOut")
        else:
            assert schema["$ref"].endswith("/AgendamentoOut")


def test_criacao_persiste_agendamento_e_comanda_sem_commit_intermediario(scenario, models):
    from decimal import Decimal
    from datetime import time

    generated_id = uuid4()

    def flush():
        appointment = scenario.db.add.call_args_list[0].args[0]
        appointment.id = generated_id
        scenario.db.commit.assert_not_called()

    scenario.db.flush.side_effect = flush
    appointment = scenario.create(
        observacoes="Preferência de corte",
        servicos=[dict(servico_id=scenario.service_id, preco="0.00", tempo_estimado=45)],
    )
    command = scenario.db.add.call_args_list[1].args[0]
    assert isinstance(command, models.Comanda)
    assert command.agendamento_id == generated_id
    assert command.cliente_id == appointment.cliente_id == scenario.payload["cliente_id"]
    assert command.barbeiro_id == appointment.barbeiro_id == scenario.professional_id
    assert appointment.criado_por == scenario.professional_id
    assert appointment.observacoes == "Preferência de corte"
    assert appointment.origem == "recepcao"
    assert appointment.status == command.status == "pendente"
    assert appointment.hora_fim == time(9, 45)
    assert command.valor_total == Decimal("0.00")
    item = command.itens[0]
    assert (item.tipo, item.descricao, item.quantidade) == ("servico", "Corte", 1)
    assert item.servico_id == scenario.service_id
    assert item.preco_unitario == Decimal("0.00")
    assert [call[0] for call in scenario.db.method_calls if call[0] in
            {"add", "flush", "commit", "refresh"}] == [
                "add", "flush", "add", "commit", "refresh",
            ]


@pytest.mark.parametrize("operation", ["flush", "commit"])
def test_falhas_persistencia_nao_sao_convertidas_em_erro_negocio(scenario, operation):
    failure = RuntimeError("Falha de persistência simulada")
    getattr(scenario.db, operation).side_effect = failure
    with pytest.raises(RuntimeError) as exc:
        scenario.create()
    assert exc.value is failure
    scenario.db.refresh.assert_not_called()
    if operation == "flush":
        scenario.db.commit.assert_not_called()
    else:
        scenario.db.commit.assert_called_once()


def test_servico_emite_erro_de_negocio_sem_http(routes, scenario, schemas):
    from app.services.agendamento import criar_agendamento
    from app.services.errors import AgendamentoInvalido

    data = schemas.AgendamentoCreate(**(scenario.payload | {"servicos": []}))
    with pytest.raises(AgendamentoInvalido, match="Informe pelo menos um serviço"):
        criar_agendamento(data, scenario.db, SimpleNamespace(id=scenario.professional_id, perfil="admin"))
    scenario.db.add.assert_not_called()
