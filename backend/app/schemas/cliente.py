from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Annotated, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator


# Mesmos limites das colunas. Não remover pontuação, espaços internos ou DDD:
# a unicidade continua comparando os valores armazenados, sem backfill.
NomeCliente = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
TelefoneCliente = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
EmailCliente = Annotated[EmailStr, Field(max_length=255)]


class PerfilClienteEntrada(BaseModel):
    data_nascimento: date | None = None
    preferencias: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None

    @field_validator('data_nascimento', mode='before')
    @classmethod
    def validar_formato_data(cls, valor):
        if valor is not None and not isinstance(valor, (str, date)):
            raise ValueError('Informe a data de nascimento no formato AAAA-MM-DD')
        if isinstance(valor, str):
            data = date.fromisoformat(valor)
            if data.isoformat() != valor:
                raise ValueError('Informe a data de nascimento no formato AAAA-MM-DD')
            return data
        return valor

    @field_validator('data_nascimento')
    @classmethod
    def validar_data_nascimento(cls, valor):
        if valor is not None and valor > datetime.now(ZoneInfo('America/Recife')).date():
            raise ValueError('A data de nascimento não pode estar no futuro')
        return valor

    @field_validator('preferencias')
    @classmethod
    def limpar_preferencias(cls, valor):
        return valor or None


class ClienteCreate(PerfilClienteEntrada):
    filial_id: UUID | None = None
    nome: NomeCliente
    telefone: TelefoneCliente
    email: Optional[EmailCliente] = None


class ClienteUpdate(PerfilClienteEntrada):
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


class ClientePerfilOut(ClienteOut):
    data_nascimento: date | None = None
    preferencias: str | None = None


class ClientePesquisaOut(BaseModel):
    """Seleção global sem dados de conta, vínculos ou informações financeiras."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    telefone: str
