from datetime import date, time, datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator
from app.schemas.reserva_publica import ProfissionalPublico


class OperacaoAgendaCliente(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    atualizado_em_esperado: datetime | None


class RemarcarCliente(OperacaoAgendaCliente):
    data: date
    hora_inicio: time
    barbeiro_id: UUID | None = None

    @field_validator('hora_inicio')
    @classmethod
    def horario_local(cls, v):
        if v.tzinfo is not None or v.second or v.microsecond or v.minute % 15:
            raise ValueError('Selecione um horario local da lista')
        return v


class ServicoMinhaAgenda(BaseModel):
    nome: str
    duracao: int
    valor: Decimal | None


class MinhaAgendaOut(BaseModel):
    id: UUID
    filial: str
    servicos: list[ServicoMinhaAgenda]
    barbeiro: ProfissionalPublico
    data: date
    hora_inicio: time
    hora_fim: time
    duracao: int
    valor: Decimal | None
    status: str
    atualizado_em: datetime | None
    proximo: bool
    pode_cancelar: bool
    pode_remarcar: bool
    fuso: str = 'America/Recife'


class OpcoesMinhaAgenda(BaseModel):
    barbeiros: list[ProfissionalPublico]
    horarios: list[str]
    fuso: str = 'America/Recife'
