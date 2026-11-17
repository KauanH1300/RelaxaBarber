from datetime import datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CancelamentoComandaCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    versao: int = Field(strict=True, ge=0)
    motivo: str = Field(min_length=1, max_length=1000)
    confirmado: bool = Field(strict=True)

    @field_validator('motivo')
    @classmethod
    def motivo_obrigatorio(cls, value):
        if not value.strip():
            raise ValueError('Informe o motivo do cancelamento')
        return value.strip()


class CancelamentoComandaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    comanda_id: UUID
    filial_id: UUID
    registrado_por: UUID
    registrado_em: datetime
    motivo: str
    chave_idempotencia: UUID
    versao: int
    status: Literal['cancelada'] = 'cancelada'
    status_anterior: Literal['pendente', 'aberta']
