import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ServicoBase(BaseModel):
    nome: str
    preco: float
    tempo_estimado: int
    comissao_padrao: float


class ServicoCreate(ServicoBase):
    pass


class ServicoUpdate(BaseModel):
    nome: str | None = None
    preco: float | None = None
    tempo_estimado: int | None = None
    comissao_padrao: float | None = None
    ativo: bool | None = None


class ServicoOut(ServicoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ativo: bool
    data_cadastro: datetime
    atualizado_em: datetime | None = None