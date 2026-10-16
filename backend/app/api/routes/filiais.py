from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.schemas.filial import FilialOut
from app.services.filiais import listar_filiais
from app.services.errors import SemPermissao

router = APIRouter(prefix="/filiais", tags=["Filiais"])


@router.get("", response_model=list[FilialOut])
def consultar_filiais(db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    try:
        return listar_filiais(db, usuario)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
