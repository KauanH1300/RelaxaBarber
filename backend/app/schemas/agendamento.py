from datetime import date, time, datetime
from decimal import Decimal
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator, model_validator
from app.schemas.valores import Duracao, Preco

class ServicoAgendamentoCreate(BaseModel):
    servico_id: UUID
    tempo_estimado: Optional[Duracao] = None  # se não vier, usa o padrão do serviço
    preco: Optional[Preco] = None       # se não vier, usa o padrão do serviço


class AgendamentoCreate(BaseModel):
    filial_id: UUID | None = None
    cliente_id: UUID
    barbeiro_id: UUID
    data: date
    hora_inicio: time
    servicos: list[ServicoAgendamentoCreate]
    observacoes: Optional[str] = None

class AgendamentoStatusUpdate(BaseModel):
    status: Literal["pendente", "aguardando","em_atendimento", "concluido", "cancelado"]
    motivo_cancelamento: str | None = None

    @field_validator("motivo_cancelamento")
    @classmethod
    def normalizar_motivo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def motivo_apenas_cancelamento(self):
        if self.motivo_cancelamento is not None and self.status != "cancelado":
            raise ValueError("Motivo de cancelamento só pode ser informado ao cancelar")
        return self

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
    filial_id: UUID
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
    cancelado_em: datetime | None = None
    cancelado_por: UUID | None = None
    motivo_cancelamento: str | None = None
    servicos: list[ServicoAgendamentoOut]
    cliente: ClienteResumo
    barbeiro: BarbeiroResumo
