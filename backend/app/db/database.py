import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.logging import install_safe_logging

install_safe_logging()

try:
    load_dotenv()
    DATABASE_URL = os.environ["DATABASE_URL"]
    opcoes_engine = {"hide_parameters": True}
    # Definido antes da primeira consulta (inclusive a autenticação). Alterar
    # isolamento dentro dos serviços seria tarde: a Session já pode ter autobegin.
    if make_url(DATABASE_URL).get_backend_name() == "postgresql":
        opcoes_engine["isolation_level"] = "READ COMMITTED"
    engine = create_engine(DATABASE_URL, **opcoes_engine)
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
