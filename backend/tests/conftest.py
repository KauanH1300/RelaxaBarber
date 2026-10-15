"""Testes sem banco: engine e carregamento de .env são proibidos.

As rotas reais são chamadas como funções, com uma sessão simulada. Não são
ensaios HTTP, transacionais ou de concorrência PostgreSQL.
"""
import importlib
import sys
from datetime import date
from decimal import Decimal
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest


def forbidden_database(*args, **kwargs):
    raise AssertionError("Etapa A: acesso ao banco de dados proibido")


@pytest.fixture(scope="session", autouse=True)
def isolated_runtime():
    import dotenv
    import sqlalchemy
    from sqlalchemy.orm import declarative_base

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dotenv, "load_dotenv", lambda *a, **kw: False)
        patch.setattr(sqlalchemy, "create_engine", forbidden_database)
        patch.setenv("SECRET_KEY", "chave-exclusivamente-ficticia-dos-testes-etapa-a")
        database = ModuleType("app.db.database")
        database.Base = declarative_base()
        database.get_db = forbidden_database
        patch.setitem(sys.modules, "app.db.database", database)
        yield


@pytest.fixture
def routes(isolated_runtime):
    return importlib.import_module("app.api.routes.agendamentos")


@pytest.fixture
def models(isolated_runtime):
    return importlib.import_module("app.models")


@pytest.fixture
def schemas(isolated_runtime):
    return importlib.import_module("app.schemas.agendamento")


@pytest.fixture
def scenario(routes, schemas, models):
    """Cenário válido e determinístico; nenhuma conexão ou commit real."""
    professional_id = UUID("00000000-0000-0000-0000-000000000001")
    service_id = UUID("00000000-0000-0000-0000-000000000002")
    service = SimpleNamespace(
        id=service_id, nome="Corte", preco=Decimal("30.00"), tempo_estimado=30,
    )
    db = MagicMock()
    service_query = MagicMock()
    service_query.filter.return_value.first.return_value = service
    professional_query = MagicMock()
    professional_query.filter.return_value.first.return_value = SimpleNamespace(
        id=professional_id, perfil="barbeiro", ativo=True,
    )
    client_query = MagicMock()
    client_query.filter.return_value.first.return_value = SimpleNamespace(ativo=True)
    appointment_query = MagicMock()
    appointment_query.filter.return_value.first.return_value = None
    db.query.side_effect = lambda model: (
        service_query if model is models.Servico else (
            professional_query if model is models.Usuario else (
                client_query if model is models.Cliente else appointment_query
            )
        )
    )
    payload = dict(
        cliente_id=uuid4(), barbeiro_id=professional_id,
        data=date(2099, 1, 1), hora_inicio="09:00:00",
        servicos=[dict(servico_id=service_id)],
    )

    def create(profile="admin", user_id=None, **changes):
        data = schemas.AgendamentoCreate(**(payload | changes))
        user = SimpleNamespace(id=user_id or professional_id, perfil=profile, ativo=True)
        return routes.criar_agendamento(data, db=db, usuario=user)

    return SimpleNamespace(
        create=create, db=db, payload=payload, professional_id=professional_id,
        service_id=service_id, service=service,
    )
