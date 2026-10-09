from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from uuid import UUID
from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.agendamento import Agendamento, AgendamentoServico
from app.models.servico import Servico
from app.schemas.agendamento import AgendamentoCreate, AgendamentoOut, AgendamentoStatusUpdate

router = APIRouter(prefix="/agendamentos", tags=["Agendamentos"])


@router.post("", response_model=AgendamentoOut, status_code=status.HTTP_201_CREATED)
def criar_agendamento(
    dados: AgendamentoCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    if not dados.servicos:
        raise HTTPException(400, "Informe pelo menos um serviço")

    # monta os itens, usando o padrão do serviço quando o front não manda valor
    itens = []
    for s in dados.servicos:
        servico = db.query(Servico).filter(Servico.id == s.servico_id, Servico.ativo == True).first()
        if not servico:
            raise HTTPException(404, "Serviço não encontrado")
        itens.append(AgendamentoServico(
            servico_id=servico.id,
            preco=s.preco if s.preco is not None else servico.preco,
            tempo_estimado=s.tempo_estimado if s.tempo_estimado is not None else servico.tempo_estimado,
        ))

    # calcula o horário de fim
    total_min = sum(i.tempo_estimado for i in itens)
    inicio = datetime.combine(dados.data, dados.hora_inicio)
    hora_fim = (inicio + timedelta(minutes=total_min)).time()

    # impede dois agendamentos sobrepostos para o mesmo barbeiro
    conflito = db.query(Agendamento).filter(
        Agendamento.barbeiro_id == dados.barbeiro_id,
        Agendamento.data == dados.data,
        Agendamento.status != "cancelado",
        Agendamento.hora_inicio < hora_fim,
        Agendamento.hora_fim > dados.hora_inicio,
    ).first()
    if conflito:
        raise HTTPException(409, "Barbeiro já tem agendamento nesse horário")

    agendamento = Agendamento(
        cliente_id=dados.cliente_id,
        barbeiro_id=dados.barbeiro_id,
        data=dados.data,
        hora_inicio=dados.hora_inicio,
        hora_fim=hora_fim,
        status="pendente",
        origem="recepcao",
        observacoes=dados.observacoes,
        criado_por=usuario.id,
        servicos=itens,
    )
    db.add(agendamento)
    db.commit()
    db.refresh(agendamento)
    return agendamento

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

TRANSICOES = {
    "pendente": {"confirmado", "concluido", "cancelado"},
    "confirmado": {"concluido", "cancelado"},
    "concluido": set(),   # estado final
    "cancelado": set(),   # estado final
}


@router.patch("/{agendamento_id}/status", response_model=AgendamentoOut)
def atualizar_status(
    agendamento_id: UUID,
    dados: AgendamentoStatusUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(get_current_user),
):
    agendamento = db.query(Agendamento).filter(Agendamento.id == agendamento_id).first()
    if not agendamento:
        raise HTTPException(404, "Agendamento não encontrado")
    if dados.status == agendamento.status:
        raise HTTPException(400, f"O agendamento já está '{agendamento.status}'")
    if dados.status not in TRANSICOES[agendamento.status]:
        raise HTTPException(
            400,
            f"Não é possível mudar de '{agendamento.status}' para '{dados.status}'",
        )

    agendamento.status = dados.status
    db.commit()
    db.refresh(agendamento)
    return agendamento