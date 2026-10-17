import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.logging import install_safe_logging

install_safe_logging()

try:
    load_dotenv()
    DATABASE_URL = os.environ["DATABASE_URL"]
    engine = create_engine(DATABASE_URL, hide_parameters=True)
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
