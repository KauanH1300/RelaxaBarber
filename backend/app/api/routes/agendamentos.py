from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.agendamento import Agendamento
from app.schemas.agendamento import AgendamentoCreate, AgendamentoOut, AgendamentoStatusUpdate
from app.services import agendamento as agendamento_service
from app.services.errors import AgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado

router = APIRouter(prefix="/agendamentos", tags=["Agendamentos"])


@router.post("", response_model=AgendamentoOut, status_code=status.HTTP_201_CREATED)
def criar_agendamento(
    dados: AgendamentoCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        return agendamento_service.criar_agendamento(dados, db, usuario)
    except AgendamentoInvalido as exc:
        raise HTTPException(400, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except HorarioOcupado as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("", response_model=list[AgendamentoOut])
def listar_agenda(
    data: date,
    barbeiro_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    q = db.query(Agendamento).filter(
        Agendamento.data == data,
        Agendamento.status != "cancelado",
    )
    if barbeiro_id:
        q = q.filter(Agendamento.barbeiro_id == barbeiro_id)
    return q.order_by(Agendamento.hora_inicio).all()


@router.patch("/{agendamento_id}/status", response_model=AgendamentoOut)
def atualizar_status(
    agendamento_id: UUID,
    dados: AgendamentoStatusUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        return agendamento_service.atualizar_status(agendamento_id, dados, db)
    except AgendamentoInvalido as exc:
        raise HTTPException(400, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
