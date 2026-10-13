from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.comanda import Comanda
from app.schemas.comanda import ComandaResponse

router = APIRouter(prefix="/comandas", tags=["Comandas"])

@router.get("", response_model=list[ComandaResponse])
def listar_comandas(
    status: str | None = None,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    query = db.query(Comanda).options(selectinload(Comanda.itens))
    if status:
        query = query.filter(Comanda.status == status)
    return query.order_by(Comanda.created_at.desc()).all()

@router.get("/{comanda_id}", response_model=ComandaResponse)
def buscar_comanda(
    comanda_id: UUID,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    comanda = (
        db.query(Comanda)
        .options(selectinload(Comanda.itens))
        .filter(Comanda.id == comanda_id)
        .first()
    )
    if not comanda:
        raise HTTPException(status_code=404, detail="Comanda não encontrada")
    return comanda