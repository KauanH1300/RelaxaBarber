"""Banco externo e carregamento de .env são proibidos.

A suíte usa sessões simuladas e, explicitamente, SQLite exclusivamente em memória
para atomicidade ORM. A fábrica controlada não aceita URL externa nem arquivo.
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

    original_create_engine = sqlalchemy.create_engine

    def create_memory_engine():
        return original_create_engine("sqlite+pysqlite:///:memory:")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dotenv, "load_dotenv", lambda *a, **kw: False)
        patch.setattr(sqlalchemy, "create_engine", forbidden_database)
        patch.setenv("SECRET_KEY", "chave-exclusivamente-ficticia-dos-testes-etapa-a")
        database = ModuleType("app.db.database")
        database.Base = declarative_base()
        database.get_db = forbidden_database
        patch.setitem(sys.modules, "app.db.database", database)
        yield create_memory_engine


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


@pytest.fixture
def memory_session(isolated_runtime, models):
    from sqlalchemy import event
    from sqlalchemy.orm import Session

    engine = isolated_runtime()

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    models.Base.metadata.create_all(engine)
    with Session(engine, autoflush=False) as session:
        yield session
    engine.dispose()


@pytest.fixture(autouse=True)
def contexto_para_sessoes_simuladas(isolated_runtime, monkeypatch):
    """Mocks da Fase 1 isolam negócio/transação; autorização real usa Session.

    Não contorna política em testes ORM/HTTP com SQLite nem PostgreSQL.
    Mantém mocks legados independentes das novas consultas de contexto.
    """
    from unittest.mock import Mock
    from app.services import filiais
    ident = UUID('97fa517c-d7d7-4e97-a9ea-e332699918fd')
    defaults = {
        'usuario_atual': lambda db, usuario, *a, **kw: usuario,
        'resolver_filial': lambda *a, **kw: SimpleNamespace(id=ident),
        'validar_profissional': lambda *a, **kw: None,
        'filial_do_registro': lambda *a, **kw: ident,
    }
    for name, simulated in defaults.items():
        original = getattr(filiais, name)
        def wrapper(db, *args, _original=original, _simulated=simulated, **kwargs):
            return _simulated(db, *args, **kwargs) if isinstance(db, Mock) else _original(db, *args, **kwargs)
        monkeypatch.setattr(filiais, name, wrapper)
