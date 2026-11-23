from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool
from app.schemas.cliente import EmailCliente


class BuscaContaParaAssociacao(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, hide_input_in_errors=True)
    presencial_id: UUID
    email: EmailCliente


class ContaParaAssociacao(BaseModel):
    id: UUID
    nome: str


class RevisaoClienteEntrada(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, hide_input_in_errors=True)
    cliente_a: UUID
    cliente_b: UUID
    versao: UUID | None
    chave: UUID
    acao: Literal['encaminhar', 'associar', 'diferentes', 'reabrir', 'desfazer']
    justificativa: str = Field(min_length=3, max_length=500)
    identidade_confirmada: StrictBool = False
    metodo: Literal['presencial_e_atendimentos', 'identidade_e_controle_da_conta',
                    'presencial_e_controle_da_conta'] | None = None
    email_conta: EmailCliente | None = None


class RevisaoClienteOut(BaseModel):
    cliente_a: UUID
    cliente_b: UUID
    estado: str
    versao: UUID
    principal_id: UUID | None


class RevisaoClienteLista(RevisaoClienteOut):
    nome_a: str
    nome_b: str
