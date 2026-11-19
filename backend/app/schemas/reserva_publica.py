from datetime import date, time
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ReservaPublicaCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    servico_id: UUID | None = None
    servicos_ids: list[UUID] | None = None
    filial_id: UUID | None = None
    barbeiro_id: UUID | None = None
    data: date
    hora_inicio: time
    chave: UUID

    @model_validator(mode='after')
    def validar_servicos(self):
        if (self.servico_id is None) == (self.servicos_ids is None):
            raise ValueError('Informe um serviço ou uma lista de serviços')
        ids = self.servicos_ids if self.servicos_ids is not None else [self.servico_id]
        if not ids or len(ids) > 20 or len(ids) != len(set(ids)):
            raise ValueError('Escolha de 1 a 20 serviços distintos')
        return self

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


class FilialPublica(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    endereco: str


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


class RestricoesUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    servicos: list[UUID]


class ServicoRestricao(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    ativo: bool


class RestricoesOut(BaseModel):
    servicos: list[ServicoRestricao]
    restricoes: list[UUID]
