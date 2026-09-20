from datetime import datetime, timedelta, timezone
import jwt
import os
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

def criar_token(usuario_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=EXPIRA_MINUTOS)
    return jwt.encode({"sub": str(usuario_id), "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

def ler_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None