import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.ambiente import configuracao_banco, exigir_tls_postgres
from app.core.logging import install_safe_logging

install_safe_logging()

try:
    url, opcoes_engine = configuracao_banco(os.environ["DATABASE_URL"])
    # Definido antes da primeira consulta (inclusive a autenticação). Alterar
    # isolamento dentro dos serviços seria tarde: a Session já pode ter autobegin.
    if url.get_backend_name() == "postgresql":
        opcoes_engine["isolation_level"] = "READ COMMITTED"
    engine = create_engine(url, **opcoes_engine)
    exigir_tls_postgres(engine)
except Exception:
    raise RuntimeError("Não foi possível configurar a conexão com o banco") from None

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
