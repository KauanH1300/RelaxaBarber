from datetime import datetime
from decimal import Decimal
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.comanda import ItemComandaResponse
from app.schemas.financeiro import DinheiroSaida


class InclusaoServicoCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    servico_id: UUID
    quantidade: int = Field(strict=True, ge=1, le=999)


class InclusaoServicoOut(BaseModel):
    item: ItemComandaResponse
    total: Decimal
    registrado_em: datetime
    registrado_por: UUID
    chave_idempotencia: UUID


class PreviaAlteracaoCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    acao: Literal['quantidade', 'substituir', 'remover']
    versao: int = Field(strict=True, ge=0)
    motivo: str = Field(min_length=1, max_length=1000)
    quantidade: int | None = Field(default=None, strict=True, ge=1, le=999)
    servico_id: UUID | None = None

    @model_validator(mode='after')
    def campos_da_operacao(self):
        if not self.motivo.strip():
            raise ValueError('Motivo obrigatório')
        if self.acao == 'quantidade' and (self.quantidade is None or self.servico_id is not None):
            raise ValueError('Informe somente a nova quantidade')
        if self.acao == 'substituir' and (self.servico_id is None or self.quantidade is None):
            raise ValueError('Informe serviço e quantidade')
        if self.acao == 'remover' and (self.servico_id is not None or self.quantidade is not None):
            raise ValueError('Remoção não aceita quantidade ou serviço')
        return self


class AlteracaoItemCreate(PreviaAlteracaoCreate):
    conferencia: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmar_fechamento: bool = Field(default=False, strict=True)


class PreviaAlteracaoOut(BaseModel):
    comanda_id: UUID
    item_id: UUID
    versao: int
    anterior: ItemComandaResponse
    posterior: ItemComandaResponse
    total_anterior: DinheiroSaida
    total: DinheiroSaida
    recebido_liquido: DinheiroSaida
    saldo: DinheiroSaida
    exige_fechamento: bool
    conferencia: str


class AlteracaoItemOut(PreviaAlteracaoOut):
    acao: Literal['quantidade', 'substituir', 'remover']
    motivo: str
    registrado_em: datetime
    registrado_por: UUID
    chave_idempotencia: UUID
    fechado: bool
