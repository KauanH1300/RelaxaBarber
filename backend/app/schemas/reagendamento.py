from datetime import date, time, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReagendamentoUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    data: date
    hora_inicio: time
    barbeiro_id: UUID
    atualizado_em_esperado: datetime | None
    motivo: str | None = Field(default=None, max_length=1000)

    @field_validator('motivo')
    @classmethod
    def normalizar_motivo(cls, value):
        return value.strip() or None if value is not None else None


class ReagendamentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    agendamento_id: UUID
    registrado_por: UUID
    registrado_em: datetime
    motivo: str | None
    data_anterior: date
    hora_inicio_anterior: time
    hora_fim_anterior: time
    barbeiro_id_anterior: UUID
    data_nova: date
    hora_inicio_nova: time
    hora_fim_nova: time
    barbeiro_id_novo: UUID
