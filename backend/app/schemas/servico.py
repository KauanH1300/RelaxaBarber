import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer

from app.schemas.valores import Comissao, Duracao, Preco


class ServicoCatalogoBase(BaseModel):
    
    # campos obrigatorios e regras de negocio basicas do serviço
    nome: str = Field(..., min_length=1)
    preco: Preco
    tempo_estimado: Duracao
 
    @field_serializer("preco", when_used="json")
    def serializar_preco(self, value) -> float:
        # Preserva o contrato JSON numérico do catálogo; cálculos usam Decimal.
        return float(value)

    @field_validator("nome")
    @classmethod
    def nome_nao_pode_ser_so_espacos(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("O campo 'nome' não pode estar vazio.")
        return v


class ServicoBase(ServicoCatalogoBase):
    comissao_padrao: Comissao

    @field_serializer("comissao_padrao", when_used="json")
    def serializar_comissao(self, value) -> float:
        return float(value)


class ServicoCreate(ServicoBase):

    # herda os campos e as validaçoes definidos em ServicoBase
    pass


class ServicoUpdate(BaseModel):
    
    # permite atualizar apenas os campos enviados na requisiçao, e quando informados, os campos continuam sujeitos as regras de validaçao
    nome: str | None = Field(None, min_length=1)
    preco: Preco | None = None
    tempo_estimado: Duracao | None = None
    comissao_padrao: Comissao | None = None
    ativo: bool | None = None

    @field_validator("nome", "preco", "tempo_estimado", "comissao_padrao", "ativo", mode="before")
    @classmethod
    def nao_permitir_null_explicito(cls, value):
        if value is None:
            raise ValueError("O campo não pode ser nulo quando enviado")
        return value
 
    @field_serializer("preco", "comissao_padrao", when_used="json")
    def serializar_preco(self, value) -> float | None:
        # Preserva o contrato JSON numérico do catálogo; cálculos usam Decimal.
        return float(value) if value is not None else None

    @field_validator("nome")
    @classmethod
    def nome_nao_pode_ser_so_espacos(cls, v: str | None) -> str | None:
        # valida o nome somente quando o campo é informado na atualizaçao
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("O campo 'nome' não pode estar vazio.")
        return v

class ServicoOut(ServicoBase):
    
    # configura o schema para receber dados diretamente de objetos ORM
    model_config = ConfigDict(from_attributes=True)
 
    id: uuid.UUID
    ativo: bool
    data_cadastro: datetime
    atualizado_em: datetime | None = None


class ServicoCatalogoOut(ServicoCatalogoBase):
    """Dados disponíveis no catálogo, sem comissão nem metadados administrativos."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ativo: bool
