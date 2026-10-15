import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, field_serializer

from app.schemas.valores import Duracao, Preco


class ServicoBase(BaseModel):
    
    # campos obrigatorios e regras de negocio basicas do serviço
    nome: str = Field(..., min_length=1)
    preco: Preco
    tempo_estimado: Duracao
    comissao_padrao: float = Field(..., gt=0)
 
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


class ServicoCreate(ServicoBase):

    # herda os campos e as validaçoes definidos em ServicoBase
    pass


class ServicoUpdate(BaseModel):
    
    # permite atualizar apenas os campos enviados na requisiçao, e quando informados, os campos continuam sujeitos as regras de validaçao
    nome: str | None = Field(None, min_length=1)
    preco: Preco | None = None
    tempo_estimado: Duracao | None = None
    comissao_padrao: float | None = Field(None, gt=0)
    ativo: bool | None = None

    @field_validator("preco", "tempo_estimado", mode="before")
    @classmethod
    def nao_permitir_null_explicito(cls, value):
        if value is None:
            raise ValueError("Preço e duração não podem ser nulos quando enviados")
        return value
 
    @field_serializer("preco", when_used="json")
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
