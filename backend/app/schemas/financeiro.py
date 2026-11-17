"""Transporte financeiro: dinheiro decimal textual e datas com offset obrigatório."""
from datetime import timezone
from decimal import Decimal
import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, BeforeValidator, ConfigDict,
    Field, PlainSerializer, StringConstraints, WithJsonSchema,
)


def decimal_textual(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", valor):
        raise ValueError("Informe dinheiro como string decimal, sem sinal ou expoente")
    return valor


def timestamp_textual(valor):
    if not isinstance(valor, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[Zz]|[+-]\d{2}:\d{2})", valor
    ):
        raise ValueError("Informe timestamp RFC3339 com timezone e precisão até microssegundos")
    return valor


DinheiroEntrada = Annotated[
    Decimal, Field(gt=0, le=Decimal('99999999.99'), multiple_of=Decimal('0.01'), allow_inf_nan=False),
    BeforeValidator(decimal_textual),
    WithJsonSchema({'type': 'string', 'pattern': r'^[0-9]+(?:\.[0-9]+)?$',
                    'description': 'Decimal positivo até 99999999.99, sem fração de centavo.',
                    'examples': ['10.00']}, mode='validation'),
]
DinheiroSaida = Annotated[
    Decimal, Field(ge=0, le=Decimal('99999999.99'), multiple_of=Decimal('0.01'), allow_inf_nan=False),
    PlainSerializer(lambda valor: format(valor, '.2f'), return_type=str, when_used='json'),
    WithJsonSchema({'type': 'string', 'pattern': r'^[0-9]+\.[0-9]{2}$'}, mode='serialization'),
]
DataEntrada = Annotated[AwareDatetime, BeforeValidator(timestamp_textual)]
DataSaida = Annotated[AwareDatetime, AfterValidator(lambda valor: valor.astimezone(timezone.utc))]
Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FormaPagamento = Literal['dinheiro', 'pix', 'debito', 'credito']


class EntradaFinanceira(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PagamentoCreate(EntradaFinanceira):
    valor: DinheiroEntrada
    forma: FormaPagamento
    recebido_em: DataEntrada


def confirmacao_explicita(valor):
    if valor is not True:
        raise ValueError('Pagamento exige confirmação explícita igual a true')
    return valor


class PagamentoConfirmadoCreate(PagamentoCreate):
    confirmado: Annotated[Literal[True], BeforeValidator(confirmacao_explicita)]


class RecebimentosCreate(EntradaFinanceira):
    pagamentos: list[PagamentoConfirmadoCreate] = Field(min_length=1, max_length=16)


class EstornoCreate(EntradaFinanceira):
    pagamento_id: UUID
    valor: DinheiroEntrada
    motivo: Motivo
    efetivado_em: DataEntrada


class FechamentoFinanceiroCreate(EntradaFinanceira):
    motivo: Motivo | None = None
    pagamentos: list[PagamentoConfirmadoCreate] = Field(default_factory=list, max_length=16)


class HabilitacaoFinanceiraCreate(EntradaFinanceira):
    conferencia: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmado: Annotated[Literal[True], BeforeValidator(confirmacao_explicita)]
    motivo: Motivo = Field(max_length=1000)


class ContextoFinanceiroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    comanda_id: UUID
    filial_id: UUID


class PagamentoHistoricoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    valor: DinheiroSaida
    forma: FormaPagamento
    recebido_em: DataSaida
    registrado_em: DataSaida


class EstornoHistoricoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    pagamento_id: UUID
    valor: DinheiroSaida
    motivo: str
    efetivado_em: DataSaida
    registrado_em: DataSaida


class HistoricoFinanceiroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pagamentos: list[PagamentoHistoricoOut] = Field(default_factory=list)
    estornos: list[EstornoHistoricoOut] = Field(default_factory=list)


class ItemConferenciaOut(BaseModel):
    id: UUID
    servico: UUID
    descricao: str
    quantidade: int
    preco: DinheiroSaida


class ConferenciaHabilitacaoOut(BaseModel):
    origem: Literal['portal_cliente']
    conferencia: str
    total: DinheiroSaida
    itens: list[ItemConferenciaOut]
    situacao: str


class HabilitacaoFinanceiraOut(ContextoFinanceiroOut):
    registrado_em: DataSaida
    registrado_por: UUID
    chave_idempotencia: UUID
    motivo: str


class ResumoFinanceiroOut(ContextoFinanceiroOut):
    situacao: Literal['nao_verificado', 'aberto', 'fechado']
    total: DinheiroSaida
    pagamentos: DinheiroSaida | None
    estornos: DinheiroSaida | None
    recebido_liquido: DinheiroSaida | None
    saldo: DinheiroSaida | None
    historico: HistoricoFinanceiroOut = Field(default_factory=HistoricoFinanceiroOut)
    habilitacao: ConferenciaHabilitacaoOut | None = None
    habilitado_em: DataSaida | None = None
    habilitado_por: UUID | None = None


class RegistroFinanceiroOut(ContextoFinanceiroOut):
    registrado_em: DataSaida
    registrado_por: UUID
    chave_idempotencia: UUID


class PagamentoOut(RegistroFinanceiroOut):
    id: UUID
    valor: DinheiroSaida
    forma: FormaPagamento
    recebido_em: DataSaida


class EstornoOut(RegistroFinanceiroOut):
    id: UUID
    pagamento_id: UUID
    valor: DinheiroSaida
    motivo: str
    efetivado_em: DataSaida


class FechamentoFinanceiroOut(RegistroFinanceiroOut):
    total: DinheiroSaida
    recebido_liquido: DinheiroSaida
    motivo: str | None


class DetalheErroFinanceiro(BaseModel):
    codigo: str
    mensagem: str


class ErroFinanceiroOut(BaseModel):
    detail: DetalheErroFinanceiro


class ErroValidacaoFinanceiraOut(BaseModel):
    # A aplicação principal usa lista de mensagens; FastAPI puro usa objetos.
    detail: list[str | dict]


class ErroAutenticacaoFinanceiraOut(BaseModel):
    detail: str
