from datetime import date, time
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator


class ReservaPublicaCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    servico_id: UUID
    barbeiro_id: UUID | None = None
    data: date
    hora_inicio: time
    chave: UUID

    @field_validator('hora_inicio')
    @classmethod
    def horario_local(cls, value):
        if value.tzinfo is not None or value.second or value.microsecond or value.minute % 15:
            raise ValueError('Selecione um horario local em passos de 15 minutos')
        return value


class ProfissionalPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str


class HorariosPublicos(BaseModel):
    data: date
    duracao: int
    fuso: str = 'America/Recife'
    horarios: list[str]


class ReservaPublicaOut(BaseModel):
    id: UUID
    status: str
    data: date
    hora_inicio: time
    hora_fim: time
    barbeiro: ProfissionalPublico
    servico: str
    fuso: str = 'America/Recife'


class HabilitacoesUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    servicos: list[UUID]
