"""Abertura e produtos de comandas avulsas."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.financeiro_errors import RotaFinanceira
from app.api.routes.financeiro import Ator, Banco, Chave, RESPOSTAS
from app.services import produtos_avulsos

router = APIRouter(prefix='/comandas', tags=['Comandas avulsas'], route_class=RotaFinanceira, responses=RESPOSTAS)


class InclusaoProduto(BaseModel):
    model_config = ConfigDict(extra='forbid')
    produto_id: UUID
    quantidade: int = Field(strict=True, ge=1, le=999)
    profissional_id: UUID | None = None


class QuantidadeProduto(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quantidade: int = Field(strict=True, ge=1, le=999)

Versao = Annotated[int | None, Query(ge=0)]


class AberturaAvulsa(BaseModel):
    model_config = ConfigDict(extra='forbid')
    cliente_id: UUID | None = None


@router.post('/avulsas', status_code=201)
def abrir(chave: Chave, db: Banco, usuario: Ator, filial_id: UUID, dados: AberturaAvulsa | None = None):
    return produtos_avulsos.abrir(db, usuario, filial_id, chave, cliente_id=dados.cliente_id if dados else None)


@router.post('/{comanda_id}/produtos')
def incluir(comanda_id: UUID, dados: InclusaoProduto, chave: Chave, db: Banco, usuario: Ator, filial_id: UUID, versao: Versao = None):
    return produtos_avulsos.alterar(db, usuario, filial_id, comanda_id, chave,
        acao='adicionar', versao=versao, **dados.model_dump())


@router.get('/{comanda_id}/produtos/historico')
def historico(comanda_id: UUID, db: Banco, usuario: Ator, filial_id: UUID):
    return produtos_avulsos.historico(db, usuario, filial_id, comanda_id)


@router.put('/{comanda_id}/produtos/{item_id}')
def quantidade(comanda_id: UUID, item_id: UUID, dados: QuantidadeProduto, chave: Chave, db: Banco, usuario: Ator, filial_id: UUID, versao: Versao = None):
    return produtos_avulsos.alterar(db, usuario, filial_id, comanda_id, chave,
        acao='quantidade', item_id=item_id, quantidade=dados.quantidade, versao=versao)


@router.delete('/{comanda_id}/produtos/{item_id}')
def remover(comanda_id: UUID, item_id: UUID, chave: Chave, db: Banco, usuario: Ator, filial_id: UUID, versao: Versao = None):
    return produtos_avulsos.alterar(db, usuario, filial_id, comanda_id, chave,
        acao='remover', item_id=item_id, versao=versao)
