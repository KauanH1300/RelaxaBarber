from datetime import datetime, timedelta, timezone
import jwt
import os
from uuid import UUID
from pwdlib import PasswordHash
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
EXPIRA_MINUTOS = 60

_hasher = PasswordHash.recommended()

def hash_senha(senha: str) -> str:
    return _hasher.hash(senha)

def verificar_senha(senha: str, senha_hash: str) -> bool:
    return _hasher.verify(senha, senha_hash)

def expira_token():
    return datetime.now(timezone.utc).replace(microsecond=0) + timedelta(minutes=EXPIRA_MINUTOS)


def criar_token(usuario_id: UUID, jti: UUID, expira: datetime) -> str:
    return jwt.encode({"sub": str(usuario_id), "jti": str(jti), "exp": expira}, SECRET_KEY, algorithm=ALGORITHM)


def ler_token(token: str) -> tuple[UUID, UUID] | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require": ["sub", "jti", "exp"]})
        return UUID(payload["sub"]), UUID(payload["jti"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None