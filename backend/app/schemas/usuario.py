from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.usuario import PerfilEnum
from app.schemas.equipe_auth import SenhaEquipe


class UsuarioCreate(BaseModel):
    filial_ids: list[UUID] | None = Field(default=None, min_length=1)
    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr
    telefone: str | None = Field(default=None, max_length=20)
    senha: SenhaEquipe
    perfil: PerfilEnum


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
    email: str
    telefone: str | None
    perfil: PerfilEnum
    ativo: bool
    data_cadastro: datetime
    email_confirmado_em: datetime | None


class UsuarioUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    nome: str = Field(min_length=2, max_length=150)
    email: EmailStr
    telefone: str | None = Field(default=None, max_length=20)
    perfil: PerfilEnum
    ativo: bool

class ProfissionalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    nome: str
