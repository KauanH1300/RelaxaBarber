from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, exigir_perfil
from app.db.database import get_db
from app.models import PerfilEnum, Usuario
from app.schemas.filial import FilialOut, VinculoUpdate, UsuarioFilialOut
from app.services import gestao_filiais
from app.services.filiais import listar_filiais
from app.services.errors import SemPermissao, RecursoNaoEncontrado, ConflitoGestaoFilial

router = APIRouter(prefix="/filiais", tags=["Filiais"])


@router.get("", response_model=list[FilialOut])
def consultar_filiais(db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    try:
        return listar_filiais(db, usuario)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc


def _executar_gestao(function, *args):
    try:
        return function(*args)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConflitoGestaoFilial as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/{filial_id}/usuarios', response_model=list[UsuarioFilialOut])
def consultar_vinculos(filial_id: UUID, db: Session = Depends(get_db),
                       usuario: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN))):
    return _executar_gestao(gestao_filiais.consultar_vinculos, db, usuario, filial_id)


@router.put('/{filial_id}/usuarios/{usuario_id}', response_model=UsuarioFilialOut)
def definir_vinculo(filial_id: UUID, usuario_id: UUID, dados: VinculoUpdate,
                     db: Session = Depends(get_db), usuario: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN))):
    return _executar_gestao(gestao_filiais.definir_vinculo, db, usuario, filial_id, usuario_id, dados.ativo)


@router.delete('/{filial_id}', status_code=status.HTTP_204_NO_CONTENT)
def desativar_filial(filial_id: UUID, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN))):
    _executar_gestao(gestao_filiais.desativar_filial, db, usuario, filial_id)
