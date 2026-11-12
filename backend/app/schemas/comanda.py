from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


class ItemComandaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tipo: str
    servico_id: UUID | None
    descricao: str
    quantidade: int
    preco_unitario: Decimal

    @computed_field
    @property
    def subtotal(self) -> Decimal:
        return self.quantidade * self.preco_unitario


class ComandaResponse(BaseModel):
    filial_id: UUID
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    agendamento_id: UUID
    cliente_id: UUID
    barbeiro_id: UUID
    status: str
    data_abertura: datetime | None
    data_fechamento: datetime | None
    itens: list[ItemComandaResponse]

    @computed_field
    @property
    def total(self) -> Decimal:
        return sum((i.subtotal for i in self.itens), Decimal("0"))


class PessoaComanda(BaseModel):
    id: UUID
    nome: str


class AtendimentoComanda(BaseModel):
    id: UUID
    data: date
    hora_inicio: time
    hora_fim: time
    status: str


class ComandaDetalhe(ComandaResponse):
    cliente: PessoaComanda
    profissional: PessoaComanda
    filial: PessoaComanda
    atendimento: AtendimentoComanda


class IndicadoresComanda(BaseModel):
    contagens: dict[str, int]
    valor_abertas: Decimal
    pagamentos_disponiveis: Literal[False] = False


class ComandaPainel(BaseModel):
    itens: list[ComandaDetalhe]
    total: int
    pagina: int
    tamanho: int
    indicadores: IndicadoresComanda
