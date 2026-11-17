from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from app.services.totais_comanda import subtotal_item, desconto, resumo_totais
from app.schemas.cancelamento_comanda import CancelamentoComandaOut

StatusApresentacao = Literal['pendente', 'aberta', 'pagamento_pendente', 'aguardando_fechamento',
                            'fechada', 'cancelada', 'nao_verificado', 'restrito']


class ItemComandaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tipo: str
    servico_id: UUID | None
    descricao: str
    quantidade: int
    ativo: bool = True
    preco_unitario: Decimal
    desconto_tipo: Literal['nenhum', 'valor', 'percentual', 'cortesia'] = 'nenhum'
    desconto_valor: Decimal = Decimal('0.00')

    @computed_field
    @property
    def subtotal_bruto(self) -> Decimal:
        return self.quantidade * self.preco_unitario

    @computed_field
    @property
    def desconto_aplicado(self) -> Decimal:
        return desconto(self.subtotal_bruto, self.desconto_tipo, self.desconto_valor)

    @computed_field
    @property
    def subtotal(self) -> Decimal:
        return subtotal_item(self)


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
    versao_itens: int = 0
    cancelamento: CancelamentoComandaOut | None = None
    desconto_tipo: Literal['nenhum', 'valor', 'percentual'] = 'nenhum'
    desconto_valor: Decimal = Decimal('0.00')
    status_apresentacao: StatusApresentacao = 'nao_verificado'
    saldo_financeiro: Decimal | None = None
    fechamento_financeiro_em: datetime | None = None

    @field_validator('cancelamento', mode='before')
    @classmethod
    def resposta_cancelamento(cls, value):
        return getattr(value, 'resultado', value)

    @field_validator('itens')
    @classmethod
    def somente_ativos(cls, itens):
        return [i for i in itens if i.ativo]

    @computed_field
    @property
    def total(self) -> Decimal:
        return resumo_totais(self.itens, self.desconto_tipo, self.desconto_valor)['total']

    @computed_field
    @property
    def descontos(self) -> dict[str, Decimal]:
        return resumo_totais(self.itens, self.desconto_tipo, self.desconto_valor)


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
    pagamentos_disponiveis: bool = True
    contagens_apresentacao: dict[str, int] = Field(default_factory=dict)
    abertas_verificadas: int = 0
    aguardando_pagamento: int = 0
    fechadas_periodo: int = 0
    escopo_financeiro: Literal['filial', 'proprias'] = 'proprias'


class ComandaPainel(BaseModel):
    itens: list[ComandaDetalhe]
    total: int
    pagina: int
    tamanho: int
    indicadores: IndicadoresComanda
