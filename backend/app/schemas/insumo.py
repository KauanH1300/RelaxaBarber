from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InsumoPadrao(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid')
    produto_id: UUID
    quantidade: Decimal = Field(gt=0, max_digits=14, decimal_places=3, allow_inf_nan=False)


class ConsumoPendente(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    produto_id: UUID
    nome: str
    unidade: str
    nao_baixada: Decimal
