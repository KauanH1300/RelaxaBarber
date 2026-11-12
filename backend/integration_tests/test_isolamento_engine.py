"""Somente consultas no PostgreSQL local validado; não usa a fixture destrutiva pg."""
from pathlib import Path
import runpy

from sqlalchemy import text


def test_engine_aplicacao_isolamento_e_reutilizacao_pool(pg_engine, monkeypatch):
    import dotenv
    from conftest import validated_url
    # Somente URL descartável já validada; não carregar configuração real.
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **kw: False)
    monkeypatch.setenv('DATABASE_URL', validated_url().render_as_string(hide_password=False))
    runtime = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'app/db/database.py'))
    engine = runtime['engine']
    try:
        with runtime['SessionLocal']() as session:
            assert session.scalar(text('SHOW transaction_isolation')) == 'read committed'
            pid = session.scalar(text('SELECT pg_backend_pid()'))
        # Checkout seguinte reutiliza a conexão física e já começa corretamente.
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT pg_backend_pid()')) == pid
            assert connection.scalar(text('SHOW transaction_isolation')) == 'read committed'
            connection.rollback()
            # Override temporário deve ser restaurado pelo SQLAlchemy no checkin.
            connection = connection.execution_options(isolation_level='SERIALIZABLE')
            assert connection.scalar(text('SHOW transaction_isolation')) == 'serializable'
        with runtime['SessionLocal']() as session:
            assert session.scalar(text('SELECT pg_backend_pid()')) == pid
            assert session.scalar(text('SHOW transaction_isolation')) == 'read committed'
        engine.dispose()
        with engine.connect() as connection:
            assert connection.scalar(text('SHOW transaction_isolation')) == 'read committed'
    finally:
        engine.dispose()
