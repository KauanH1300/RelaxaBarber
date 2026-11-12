from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator


# Mesmos limites das colunas. Não remover pontuação, espaços internos ou DDD:
# a unicidade continua comparando os valores armazenados, sem backfill.
NomeCliente = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
TelefoneCliente = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
EmailCliente = Annotated[EmailStr, Field(max_length=255)]


class ClienteCreate(BaseModel):
    filial_id: UUID | None = None
    nome: NomeCliente
    telefone: TelefoneCliente
    email: Optional[EmailCliente] = None


class ClienteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: Optional[NomeCliente] = None
    telefone: Optional[TelefoneCliente] = None
    email: Optional[EmailCliente] = None

    @field_validator('nome', 'telefone', mode='before')
    @classmethod
    def rejeitar_null_explicito(cls, valor: object) -> object:
        # Defaults omitidos não passam por este validator. A rota já usa
        # exclude_unset=True; somente campos enviados serão persistidos.
        if valor is None:
            raise ValueError('O campo não pode ser null')
        return valor


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
