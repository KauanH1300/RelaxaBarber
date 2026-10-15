from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import exigir_perfil, get_current_user
from app.core.security import hash_senha
from app.db.database import get_db
from app.models.usuario import PERFIS_PROFISSIONAIS, PerfilEnum, Usuario
from app.services.errors import SemPermissao
from app.services.permissoes_agendamento import escopo_consulta
from app.schemas.usuario import UsuarioCreate, UsuarioOut, ProfissionalOut

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
@router.get("", response_model=list[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    return db.scalars(select(Usuario).order_by(Usuario.nome)).all()

@router.get("/barbeiros", response_model=list[ProfissionalOut])
def listar_barbeiros(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    try:
        profissional_id = escopo_consulta(usuario, None)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    query = select(Usuario).where(
        Usuario.ativo.is_(True), Usuario.perfil.in_(PERFIS_PROFISSIONAIS),
    )
    if profissional_id is not None:
        query = query.where(Usuario.id == profissional_id)
    return db.scalars(query.order_by(Usuario.nome)).all()
