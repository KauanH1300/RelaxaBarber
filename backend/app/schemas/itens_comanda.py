from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.comanda import ItemComandaResponse


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
