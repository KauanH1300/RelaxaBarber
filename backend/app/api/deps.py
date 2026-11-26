from fastapi import Depends, HTTPException, status
from fastapi import Request
from app.core.cookies_equipe import COOKIE, csrf
from sqlalchemy.orm import Session
from app.services import sessoes_equipe
from app.db.database import get_db
from app.models.usuario import Usuario

def oauth2(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Não autenticado")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf(request)
    return token

def get_current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> Usuario:
    usuario = sessoes_equipe.validar(db, token)
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado")
    return usuario

def exigir_perfil(*perfis: str):
    def checar(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.perfil not in perfis:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão")
        return usuario
    return checar