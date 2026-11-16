import re
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.cliente import NomeCliente, EmailCliente


def telefone_normalizado(value):
    digits = re.sub(r'\D', '', value)
    if len(digits) in (10, 11):
        digits = '55' + digits
    return digits


class Entrada(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


class ContatoPortal(Entrada):
    email: EmailCliente

    @field_validator('email')
    @classmethod
    def normalizar_email(cls, value):
        return str(value).lower()


class CadastroPortal(ContatoPortal):
    nome: NomeCliente
    telefone: str = Field(min_length=10, max_length=25)
    senha: str = Field(min_length=12, max_length=128)

    @field_validator('telefone')
    @classmethod
    def telefone_valido(cls, value):
        if not re.fullmatch(r'[\d+().\s-]+', value):
            raise ValueError('Informe telefone com DDD e apenas pontuação telefônica')
        value = telefone_normalizado(value)
        if not 12 <= len(value) <= 15:
            raise ValueError('Informe telefone válido com DDD')
        return value


class ConfirmarPortal(Entrada):
    solicitacao_id: UUID
    codigo: str = Field(pattern=r'^\d{6}$')


class TrocarEmailPortal(Entrada):
    email_novo: EmailCliente

    @field_validator('email_novo')
    @classmethod
    def normalizar_novo(cls, value):
        return str(value).lower()


class RedefinirPortal(ConfirmarPortal):
    senha: str = Field(min_length=12, max_length=128)


class LoginPortal(ContatoPortal):
    senha: str = Field(min_length=1, max_length=128)


class PerfilPortal(Entrada):
    model_config = ConfigDict(from_attributes=True, extra='forbid')
    id: UUID
    nome: str
    email: str | None
    telefone: str
