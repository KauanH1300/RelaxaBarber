from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import exigir_perfil
from app.core.security import hash_senha
from app.db.database import get_db
from app.models.usuario import PerfilEnum, Usuario
from app.schemas.usuario import UsuarioCreate, UsuarioOut

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    dados: UsuarioCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    email = dados.email.lower()
    if db.scalar(select(Usuario).where(Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado")

    usuario = Usuario(
        nome=dados.nome,
        email=email,
        telefone=dados.telefone,
        senha_hash=hash_senha(dados.senha),
        perfil=dados.perfil,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario