from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.comanda import Comanda
from app.services import filiais
from app.services.errors import SemPermissao, FilialObrigatoria, AgendamentoInvalido, RecursoNaoEncontrado
from app.services.permissoes_agendamento import escopo_consulta
from app.schemas.comanda import ComandaResponse, ComandaDetalhe, ComandaPainel
from app.services import comandas as consultas

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

@router.get("/painel", response_model=ComandaPainel)
def painel_comandas(
    pagina: int = Query(1, ge=1),
    tamanho: int = Query(6, ge=1, le=48),
    busca: str = Query('', max_length=100),
    status: Literal['pendente', 'aberta', 'fechada', 'cancelada'] | None = None,
    profissional_id: UUID | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    filial_id: UUID | None = None,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    try:
        return consultas.consultar_painel(
            db, usuario, filial_id, pagina=pagina, tamanho=tamanho, busca=busca,
            status=status, profissional_id=profissional_id,
            data_inicio=data_inicio, data_fim=data_fim,
        )
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except (FilialObrigatoria, AgendamentoInvalido) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{comanda_id}", response_model=ComandaDetalhe)
def buscar_comanda(
    comanda_id: UUID,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
    filial_id: UUID | None = None,
):
    try:
        return consultas.buscar_detalhe(db, usuario, comanda_id, filial_id)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
