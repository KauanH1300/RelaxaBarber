from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.comanda import Comanda
from app.services import filiais
from app.services.errors import SemPermissao, FilialObrigatoria
from app.services.permissoes_agendamento import escopo_consulta
from app.schemas.comanda import ComandaResponse

router = APIRouter(prefix="/comandas", tags=["Comandas"])

@router.get("", response_model=list[ComandaResponse])
def listar_comandas(
    status: str | None = None,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
    filial_id: UUID | None = None,
):
    try:
        usuario = filiais.usuario_atual(db, usuario)
        filial = filiais.resolver_filial(db, usuario, filial_id)
        profissional_id = escopo_consulta(usuario, None)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc
    query = db.query(Comanda).options(selectinload(Comanda.itens)).filter(Comanda.filial_id == filial.id)
    if profissional_id is not None:
        query = query.filter(Comanda.barbeiro_id == profissional_id)
    if status:
        query = query.filter(Comanda.status == status)
    return query.order_by(Comanda.created_at.desc()).all()

@router.get("/{comanda_id}", response_model=ComandaResponse)
def buscar_comanda(
    comanda_id: UUID,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
    filial_id: UUID | None = None,
):
    try:
        usuario = filiais.usuario_atual(db, usuario)
        filtros = filiais.filtro_acesso(usuario, Comanda)
        if filial_id is not None:
            filtros.append(Comanda.filial_id == filial_id)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    comanda = (
        db.query(Comanda)
        .options(selectinload(Comanda.itens))
        .filter(Comanda.id == comanda_id, *filtros)
        .first()
    )
    if not comanda:
        raise HTTPException(status_code=404, detail="Comanda não encontrada")
    return comanda
