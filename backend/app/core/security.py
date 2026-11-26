from datetime import datetime, timedelta, timezone
import jwt
import os
from uuid import UUID
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from argon2 import Type
from pwdlib.hashers.argon2 import Argon2Hasher
from threading import BoundedSemaphore
from functools import lru_cache
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
EXPIRA_MINUTOS = 60

_hasher = PasswordHash((Argon2Hasher(
    type=Type.ID, time_cost=3, memory_cost=65536,
    parallelism=4, salt_len=16, hash_len=32,
),))
# One 64 MiB operation per worker; no unbounded request queue waiting for memory.
_slots = BoundedSemaphore(1)


def _operar(function, *args):
    if not _slots.acquire(blocking=False):
        raise HTTPException(503, "Autenticação ocupada. Tente novamente em instantes.",
                            headers={"Retry-After": "2"})
    try:
        return function(*args)
    finally:
        _slots.release()


@lru_cache(maxsize=1)
def hash_ficticio():
    return hash_senha("comparacao-interna-sem-conta-real")


def autenticar_senha(senha, senha_hash):
    if not isinstance(senha, str) or not 1 <= len(senha) <= 128:
        return False, None
    try:
        return _operar(_hasher.verify_and_update, senha, senha_hash)
    except (UnknownHashError, ValueError):
        return False, None


def hash_senha(senha: str) -> str:
    return _operar(_hasher.hash, senha)

def verificar_senha(senha: str, senha_hash: str) -> bool:
    return autenticar_senha(senha, senha_hash)[0]

def expira_token():
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=EXPIRA_MINUTOS)


def criar_token(usuario_id: UUID, jti: UUID, expira: datetime) -> str:
    return jwt.encode({"sub": str(usuario_id), "jti": str(jti), "exp": expira, "transport": "cookie-v1"}, SECRET_KEY, algorithm=ALGORITHM)


def ler_token(token: str) -> tuple[UUID, UUID] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["sub", "jti", "exp"]})
        if payload.get("transport") != "cookie-v1":
            return None
        return UUID(payload["sub"]), UUID(payload["jti"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None