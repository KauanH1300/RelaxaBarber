"""Respostas sanitizadas para falhas de persistência, inclusive nas consultas."""
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, OperationalError, DisconnectionError, TimeoutError

from app.services.persistencia import (
    BancoIndisponivel, ConflitoPersistencia, FalhaPersistencia, traduzir_erro,
)

logger = logging.getLogger(__name__)


async def falha_persistencia_handler(request: Request, exc: FalhaPersistencia):
    codigo = 409 if isinstance(exc, ConflitoPersistencia) else 503 if isinstance(exc, BancoIndisponivel) else 500
    return JSONResponse(status_code=codigo, content={"detail": exc.mensagem})


async def erro_sqlalchemy_handler(request: Request, exc: SQLAlchemyError):
    if isinstance(exc, (OperationalError, DisconnectionError, TimeoutError)):
        return await falha_persistencia_handler(request, traduzir_erro(exc))
    # Erros de programação permanecem identificáveis internamente; não viram
    # conflito de negócio e não expõem SQL ou argumentos pela resposta HTTP.
    logger.error(
        "Erro inesperado de banco: classe=%s locais=%s", type(exc).__name__,
        [(frame.filename, frame.lineno, frame.name) for frame in traceback.extract_tb(exc.__traceback__)],
    )
    return JSONResponse(status_code=500, content={"detail": FalhaPersistencia.mensagem})


def registrar_erros_persistencia(app: FastAPI) -> None:
    app.add_exception_handler(FalhaPersistencia, falha_persistencia_handler)
    app.add_exception_handler(SQLAlchemyError, erro_sqlalchemy_handler)
