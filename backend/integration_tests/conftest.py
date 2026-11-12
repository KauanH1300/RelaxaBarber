"""Suíte opt-in, separada dos testes sem banco. Nunca carrega o .env."""
import importlib
import os
from pathlib import Path
import sys
from types import ModuleType

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base

ROOT = Path(__file__).resolve().parents[1]


def pytest_collection_modifyitems(items):
    integration = Path(__file__).resolve().parent
    if any(not Path(item.path).resolve().is_relative_to(integration) for item in items):
        raise pytest.UsageError('Execute integração e regressão em processos separados; informe backend/integration_tests explicitamente')


sys.path.insert(0, str(ROOT))


def validated_url():
    raw = os.environ.get('RELAXABARBER_TEST_DATABASE_URL')
    if not raw:
        pytest.skip('PostgreSQL descartável não autorizado/configurado')
    url = make_url(raw)
    # Alvo fixo e exclusivo; não aceitar DNS, socket, opções de host ou serviço.
    if not (url.drivername == 'postgresql+psycopg2' and url.host == '127.0.0.1'
            and url.port == 55432 and url.database == 'relaxabarber_concorrencia_test'
            and url.username == 'rb_concorrencia_test' and not url.query):
        raise pytest.UsageError('Destino de integração recusado: exige PostgreSQL local exclusivo')
    from dotenv import dotenv_values
    for candidate in (ROOT.parent / '.env', ROOT / '.env'):
        value = dotenv_values(candidate, interpolate=False).get('DATABASE_URL') if candidate.exists() else None
        if value:
            app = make_url(value)
            if (app.host in ('127.0.0.1', 'localhost', '::1') and (app.port or 5432) == url.port and app.database == url.database):
                raise pytest.UsageError('Destino de testes coincide com banco da aplicação')
    value = os.environ.get('DATABASE_URL')
    if value:
        app = make_url(value)
        if (app.host in ('127.0.0.1', 'localhost', '::1') and (app.port or 5432) == url.port and app.database == url.database):
            raise pytest.UsageError('Destino de testes coincide com DATABASE_URL da aplicação')
    return url


@pytest.fixture(scope='session')
def pg_engine():
    url = validated_url()  # valida antes de importar app ou abrir conexão
    engine = create_engine(url, connect_args={'connect_timeout': 3}, pool_size=4, max_overflow=0)
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT current_database()')) == 'relaxabarber_concorrencia_test'
        assert conn.scalar(text('SELECT current_user')) == 'rb_concorrencia_test'
    from runtime_roles import provisionar_papeis
    provisionar_papeis(engine)
    with pytest.MonkeyPatch.context() as patch:
        import dotenv
        patch.setattr(dotenv, 'load_dotenv', lambda *a, **kw: False)
        patch.setenv('SECRET_KEY', 'chave-ficticia-exclusiva-da-integracao-local')
        database = ModuleType('app.db.database')
        database.Base = declarative_base()
        def exigir_sessao_explicita():
            raise AssertionError('Integração exige sessão explícita do PostgreSQL descartável')
        database.get_db = exigir_sessao_explicita
        patch.setitem(sys.modules, 'app.db.database', database)
        importlib.import_module('app.models')
        yield engine
    engine.dispose()


@pytest.fixture
def pg(pg_engine):
    # Este banco é descartável; cada teste recebe a cadeia real de migrations.
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    config = Config()
    config.set_main_option('script_location', str(ROOT / 'alembic'))
    scripts = ScriptDirectory.from_config(config)
    with pg_engine.begin() as conn:
        conn.execute(text('DROP SCHEMA public CASCADE'))
        conn.execute(text('CREATE SCHEMA public AUTHORIZATION rb_horarios_migrador'))
        conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        # O schema anterior foi eliminado: seus defaults também foram removidos.
        # Recriar defaults amplos aqui garante que cada migração seja desafiada.
        conn.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES '
                          'TO PUBLIC, anon, authenticated, service_role, relaxabarber_runtime'))
        for revision in reversed(list(scripts.walk_revisions())):
            with Operations.context(MigrationContext.configure(conn)):
                revision.module.upgrade()
    yield pg_engine


@pytest.fixture
def runtime_pg(pg):
    from runtime_roles import conceder_runtime_legado, engine_login
    conceder_runtime_legado(pg)
    engine = engine_login(pg)
    try:
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT current_user')) == 'relaxabarber_dev_app'
            assert not conn.scalar(text("SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname=current_user"))
        yield engine
    finally:
        engine.dispose()
