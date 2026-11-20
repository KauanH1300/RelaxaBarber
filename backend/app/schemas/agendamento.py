from datetime import date, time, datetime
from decimal import Decimal
from typing import Annotated, Optional, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator, model_validator
from app.schemas.insumo import ConsumoPendente
from app.schemas.valores import Duracao, Preco

ObservacoesAtendimento = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


class ObservacoesAgendamentoUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    observacoes: ObservacoesAtendimento | None
    atualizado_em_esperado: datetime | None


class ServicoAgendamentoCreate(BaseModel):
    servico_id: UUID
    tempo_estimado: Optional[Duracao] = None  # se não vier, usa o padrão do serviço
    preco: Optional[Preco] = None       # se não vier, usa o padrão do serviço


class AtendimentoImediatoCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    chave_idempotencia: UUID | None = None
    filial_id: UUID | None = None
    cliente_id: UUID
    barbeiro_id: UUID
    servicos: list[ServicoAgendamentoCreate]
    observacoes: ObservacoesAtendimento | None = None
    duracao_min: Duracao | None = None


class AgendamentoCreate(AtendimentoImediatoCreate):
    model_config = ConfigDict(extra='ignore')
    data: date
    hora_inicio: time

class AgendamentoStatusUpdate(BaseModel):
    status: Literal["pendente", "aguardando","em_atendimento", "concluido", "cancelado", "nao_compareceu"]
    motivo_cancelamento: str | None = None
    falta_motivo: str | None = None
    atualizado_em_esperado: datetime | None = None
    confirmado: StrictBool = False

    @field_validator("motivo_cancelamento", "falta_motivo")
    @classmethod
    def normalizar_motivo(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def motivo_apenas_cancelamento(self):
        if self.status == 'cancelado':
            if not self.motivo_cancelamento or len(self.motivo_cancelamento) > 1000:
                raise ValueError('Informe um motivo de cancelamento com até 1000 caracteres')
            if not self.confirmado or self.atualizado_em_esperado is None:
                raise ValueError('Cancelamento exige confirmação explícita e versão esperada')
        if self.motivo_cancelamento is not None and self.status != "cancelado":
            raise ValueError("Motivo de cancelamento só pode ser informado ao cancelar")
        if self.status == 'nao_compareceu':
            if not self.falta_motivo or len(self.falta_motivo) > 1000:
                raise ValueError('Informe o motivo do não comparecimento com até 1000 caracteres')
            if not self.confirmado or self.atualizado_em_esperado is None:
                raise ValueError('Não comparecimento exige confirmação explícita e versão esperada')
        elif self.falta_motivo is not None:
            raise ValueError('Motivo da falta só pode ser informado ao registrar não comparecimento')
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
    cancelado_por_cliente: UUID | None = None
    motivo_cancelamento: str | None = None
    falta_registrada_em: datetime | None = None
    falta_registrada_por: UUID | None = None
    falta_motivo: str | None = None
    divergencias_insumos: list[ConsumoPendente] = Field(default_factory=list)
    servicos: list[ServicoAgendamentoOut]
    atualizado_em: datetime | None = None
    cliente: ClienteResumo
    barbeiro: BarbeiroResumo
