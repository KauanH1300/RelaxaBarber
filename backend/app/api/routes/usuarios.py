from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import exigir_perfil, get_current_user
from app.core.security import hash_senha
from app.db.database import get_db
from app.models.usuario import PERFIS_PROFISSIONAIS, PerfilEnum, Usuario
from app.services.errors import SemPermissao, FilialObrigatoria
from app.services import filiais
from app.models.usuario_filial import UsuarioFilial
from app.services.permissoes_agendamento import escopo_consulta
from app.schemas.usuario import UsuarioCreate, UsuarioOut, ProfissionalOut

from app.services.persistencia import transacao_escrita, recarregar_confirmado

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    dados: UsuarioCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    with transacao_escrita(db):
        try:
            atual = filiais.usuario_atual(db, _, bloquear=True)
            if atual.perfil != PerfilEnum.ADMIN:
                raise SemPermissao("Sem permissão")
            ids = dados.filial_ids
            if ids:
                unidades = [
                    filiais.resolver_filial(db, atual, filial_id, bloquear=True)
                    for filial_id in sorted(set(ids), key=str)
                ]
            else:
                unidades = [filiais.resolver_filial(db, atual, bloquear=True)]
        except SemPermissao as exc:
            raise HTTPException(403, str(exc)) from exc
        except FilialObrigatoria as exc:
            raise HTTPException(422, str(exc)) from exc
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
        db.flush()
        db.add_all([UsuarioFilial(usuario_id=usuario.id, filial_id=unidade.id) for unidade in unidades])
    recarregar_confirmado(db, usuario)
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
    filial_id: UUID | None = None,
):
    try:
        usuario = filiais.usuario_atual(db, usuario)
        filial = filiais.resolver_filial(db, usuario, filial_id)
        profissional_id = escopo_consulta(usuario, None)
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    query = select(Usuario).join(UsuarioFilial, UsuarioFilial.usuario_id == Usuario.id).where(
        UsuarioFilial.filial_id == filial.id, UsuarioFilial.ativo.is_(True),
        Usuario.ativo.is_(True), Usuario.perfil.in_(PERFIS_PROFISSIONAIS),
    )
    if profissional_id is not None:
        query = query.where(Usuario.id == profissional_id)
    return db.scalars(query.order_by(Usuario.nome)).all()
