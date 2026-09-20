from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import criar_token, verificar_senha
from app.db.database import get_db
from app.models.usuario import Usuario
router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    usuario = db.scalar(select(Usuario).where(Usuario.email == form.username))
    if not usuario or not verificar_senha(form.password, usuario.senha_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
    if not usuario.ativo:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Conta desativada")
    return {"access_token": criar_token(usuario.id), "token_type": "bearer"}

@router.get("/me")
def me(usuario: Usuario = Depends(get_current_user)):
    return {"id": usuario.id, "email": usuario.email, "perfil": usuario.perfil}