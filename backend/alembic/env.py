"""Configuração Alembic sem enviar credenciais ao ConfigParser."""
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from app.core.logging import install_safe_logging

install_safe_logging()


def run_migrations() -> None:
    config = context.config
    if config.config_file_name is not None:
        fileConfig(config.config_file_name)
    load_dotenv()
    database_url = os.environ["DATABASE_URL"]

    from app.db.database import Base
    import app.models  # Registra todos os modelos no metadata.

    if context.is_offline_mode():
        context.configure(
            url=database_url,
            target_metadata=Base.metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    # Não colocar DATABASE_URL em config.set_main_option: percentuais de senhas
    # e parâmetros seriam interpretados, e o erro poderia incluir a URL inteira.
    engine = create_engine(database_url, poolclass=pool.NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


try:
    run_migrations()
except Exception:
    # O CLI também pode formatar o erro: não propagar mensagens do driver ou
    # configuração. Os context managers acima preservam rollback e descarte.
    raise RuntimeError("Falha no Alembic; verifique a configuração privada e o banco") from None
