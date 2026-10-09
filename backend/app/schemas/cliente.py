from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr


class ClienteCreate(BaseModel):
    nome: str
    telefone: str
    email: Optional[EmailStr] = None


class ClienteUpdate(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    email: Optional[EmailStr] = None


class ClienteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    telefone: str
    email: Optional[str]
    conta_ativada: bool
    saldo: Decimal
    ativo: bool
    data_cadastro: datetime