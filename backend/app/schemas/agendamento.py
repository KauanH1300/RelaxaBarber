from datetime import date, time
from decimal import Decimal
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict

class ServicoAgendamentoCreate(BaseModel):
    servico_id: UUID
    tempo_estimado: Optional[int] = None  # se não vier, usa o padrão do serviço
    preco: Optional[Decimal] = None       # se não vier, usa o padrão do serviço


class AgendamentoCreate(BaseModel):
    cliente_id: UUID
    barbeiro_id: UUID
    data: date
    hora_inicio: time
    servicos: list[ServicoAgendamentoCreate]
    observacoes: Optional[str] = None

class AgendamentoStatusUpdate(BaseModel):
    status: Literal["pendente", "confirmado", "concluido", "cancelado"]
    
class ClienteResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    telefone: str


class BarbeiroResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str


class ServicoResumo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str

class ServicoAgendamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    servico_id: UUID
    preco: Decimal
    tempo_estimado: int
    servico: ServicoResumo

class AgendamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cliente_id: UUID
    barbeiro_id: UUID
    data: date
    hora_inicio: time
    hora_fim: time
    status: str
    origem: str
    observacoes: Optional[str]
    servicos: list[ServicoAgendamentoOut]
    cliente: ClienteResumo   
    barbeiro: BarbeiroResumo 