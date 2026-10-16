from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr


class ClienteCreate(BaseModel):
    filial_id: UUID | None = None
    nome: str
    telefone: str
    email: Optional[EmailStr] = None


class ClienteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    ativo: bool
    data_cadastro: datetime


class ClientePesquisaOut(BaseModel):
    """Seleção global sem dados de conta, vínculos ou informações financeiras."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    telefone: str
