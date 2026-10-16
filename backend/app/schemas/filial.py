from uuid import UUID
from pydantic import BaseModel, ConfigDict


class FilialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    fuso_horario: str


class VinculoUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ativo: bool


class UsuarioFilialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    usuario_id: UUID
    filial_id: UUID
    ativo: bool
