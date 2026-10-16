from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.schemas.agendamento import AgendamentoCreate, AgendamentoOut, AgendamentoStatusUpdate
from app.services import agendamento as agendamento_service
from app.services.errors import FilialObrigatoria, AgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado, SemPermissao, HorarioAgendamentoInvalido, ValoresAgendamentoInvalidos, ClienteInativo, ConflitoEstadoAgendamento

router = APIRouter(prefix="/agendamentos", tags=["Agendamentos"])


@router.post("", response_model=AgendamentoOut, status_code=status.HTTP_201_CREATED)
def criar_agendamento(
    dados: AgendamentoCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        return agendamento_service.criar_agendamento(dados, db, usuario)
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except ClienteInativo as exc:
        raise HTTPException(409, str(exc)) from exc
    except (HorarioAgendamentoInvalido, ValoresAgendamentoInvalidos) as exc:
        raise HTTPException(422, str(exc)) from exc
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
    filial_id: UUID | None = None,
):
    try:
        return agendamento_service.listar_agenda(data, barbeiro_id, db, usuario, filial_id)
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc


@router.patch("/{agendamento_id}/status", response_model=AgendamentoOut)
def atualizar_status(
    agendamento_id: UUID,
    dados: AgendamentoStatusUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
    filial_id: UUID | None = None,
):
    try:
        return agendamento_service.atualizar_status(agendamento_id, dados, db, usuario, filial_id)
    except ConflitoEstadoAgendamento as exc:
        raise HTTPException(409, str(exc)) from exc
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except AgendamentoInvalido as exc:
        raise HTTPException(400, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{agendamento_id}", response_model=AgendamentoOut)
def buscar_agendamento(agendamento_id: UUID, db: Session = Depends(get_db), usuario=Depends(get_current_user), filial_id: UUID | None = None):
    try:
        return agendamento_service.buscar_agendamento(agendamento_id, db, usuario, filial_id)
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
