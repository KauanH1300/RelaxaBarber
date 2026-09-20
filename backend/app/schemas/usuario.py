from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.usuario import PerfilEnum


class UsuarioCreate(BaseModel):
    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr
    telefone: str | None = Field(default=None, max_length=20)
    senha: str = Field(min_length=8, max_length=128)
    perfil: PerfilEnum


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: EmailStr
    telefone: str | None
    perfil: PerfilEnum
    ativo: bool
    data_cadastro: datetime