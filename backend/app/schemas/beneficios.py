from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator
from app.schemas.comanda import ItemComandaResponse
from app.schemas.financeiro import DinheiroSaida

# Bases históricas podem exceder o limite do total líquido ao acumular linhas.
DinheiroCalculo = Annotated[Decimal, Field(ge=0, multiple_of=Decimal('0.01'), allow_inf_nan=False),
    PlainSerializer(lambda v: format(v, '.2f'), return_type=str, when_used='json')]


class BeneficioPreviaCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    acao: Literal['item', 'comanda', 'encerramento_gratuito']
    versao: int = Field(strict=True, ge=0)
    motivo: str = Field(min_length=1, max_length=1000)
    item_id: UUID | None = None
    desconto_tipo: Literal['nenhum', 'valor', 'percentual', 'cortesia'] = 'nenhum'
    desconto_valor: Decimal = Field(default=Decimal('0.00'), ge=0, le=Decimal('99999999.99'), max_digits=10, decimal_places=2, allow_inf_nan=False)

    @field_validator('desconto_valor')
    @classmethod
    def centavos(cls, valor):
        return valor.quantize(Decimal('0.01'))

    @model_validator(mode='after')
    def validar(self):
        if not self.motivo.strip():
            raise ValueError('Motivo obrigatório')
        if (self.acao == 'item') != (self.item_id is not None):
            raise ValueError('Informe item somente para benefício individual')
        if self.desconto_tipo == 'cortesia' and self.acao != 'item':
            raise ValueError('Cortesia integral é individual por serviço')
        if self.desconto_tipo in ('nenhum', 'cortesia') and self.desconto_valor != 0:
            raise ValueError('Nenhum/cortesia não aceita valor adicional')
        if self.desconto_tipo == 'percentual' and self.desconto_valor > 100:
            raise ValueError('Percentual máximo de 100%')
        if self.acao == 'encerramento_gratuito' and (self.desconto_tipo != 'nenhum' or self.desconto_valor != 0):
            raise ValueError('Encerramento não altera descontos')
        return self


class BeneficioCreate(BeneficioPreviaCreate):
    conferencia: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmar_fechamento: bool = Field(default=False, strict=True)
    confirmar_gratuidade: bool = Field(default=False, strict=True)


class EstadoBeneficios(BaseModel):
    itens: list[ItemComandaResponse]
    desconto_tipo: str
    desconto_valor: DinheiroSaida
    total_bruto: DinheiroCalculo
    desconto_itens: DinheiroCalculo
    subtotal: DinheiroCalculo
    desconto_geral: DinheiroCalculo
    total: DinheiroSaida


class BeneficioPreviaOut(BaseModel):
    comanda_id: UUID
    versao: int
    anterior: EstadoBeneficios
    posterior: EstadoBeneficios
    recebido_liquido: DinheiroSaida
    saldo: DinheiroSaida
    exige_fechamento: bool
    exige_gratuidade: bool
    conferencia: str


class BeneficioOut(BeneficioPreviaOut):
    acao: Literal['item', 'comanda', 'encerramento_gratuito']
    item_id: UUID | None
    motivo: str
    registrado_por: UUID
    registrado_em: datetime
    chave_idempotencia: UUID
    fechado: bool
