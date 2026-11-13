"""Adaptadores HTTP dos serviços financeiros por comanda."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.financeiro_errors import RotaFinanceira
from app.db.database import get_db
from app.models.usuario import Usuario
from app.schemas.financeiro import (
    PagamentoCreate, PagamentoOut, EstornoCreate, EstornoOut,
    FechamentoFinanceiroCreate, FechamentoFinanceiroOut, ResumoFinanceiroOut,
    ErroFinanceiroOut, ErroValidacaoFinanceiraOut, ErroAutenticacaoFinanceiraOut,
)
from app.services import financeiro

RESPOSTAS = {
    401: {'model': ErroAutenticacaoFinanceiraOut, 'description': 'Credencial ausente ou inválida'},
    403: {'model': ErroFinanceiroOut, 'description': 'Permissão financeira negada'},
    404: {'model': ErroFinanceiroOut, 'description': 'Recurso inexistente ou fora do escopo'},
    409: {'model': ErroFinanceiroOut, 'description': 'Conflito de estado, saldo, legado ou idempotência'},
    422: {'model': ErroFinanceiroOut | ErroValidacaoFinanceiraOut, 'description': 'Entrada inválida'},
    500: {'model': ErroFinanceiroOut, 'description': 'Falha interna sanitizada'},
    503: {'model': ErroFinanceiroOut, 'description': 'Indisponibilidade, abortamento ou confirmação indeterminada'},
}
router = APIRouter(prefix='/comandas', tags=['Financeiro'], route_class=RotaFinanceira, responses=RESPOSTAS)
Banco = Annotated[Session, Depends(get_db)]
Ator = Annotated[Usuario, Depends(get_current_user)]
Chave = Annotated[UUID, Header(alias='Idempotency-Key', description='UUID persistido antes do envio; repetir a mesma chave e payload após timeout')]


@router.get('/{comanda_id}/financeiro', response_model=ResumoFinanceiroOut,
            summary='Consultar situação financeira da comanda')
def consultar(comanda_id: UUID, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    """Barbeiros consultam somente próprias comandas. Legado retorna saldo null."""
    return financeiro.consultar_situacao(comanda_id, db, usuario, filial_id)


@router.post('/{comanda_id}/pagamentos', response_model=PagamentoOut,
             summary='Registrar ou recuperar pagamento idempotente')
def pagar(comanda_id: UUID, dados: PagamentoCreate, chave: Chave, db: Banco,
          usuario: Ator, filial_id: UUID | None = None):
    """Exige conclusão operacional. Retroatividade: 168 horas inclusivas, exceto ADMIN.

    Criação e replay retornam 200. A mesma chave com outro payload retorna 409.
    Pagamento integral não fecha financeiramente a comanda.
    """
    return financeiro.registrar_pagamento(comanda_id, **dados.model_dump(),
        chave_idempotencia=chave, db=db, usuario=usuario, filial_id=filial_id)


@router.post('/{comanda_id}/estornos', response_model=EstornoOut,
             summary='Registrar ou recuperar estorno idempotente (ADMIN)')
def estornar(comanda_id: UUID, dados: EstornoCreate, chave: Chave, db: Banco,
             usuario: Ator, filial_id: UUID | None = None):
    """Somente ADMIN. Motivo obrigatório; sem exceder o pagamento ou antecedê-lo."""
    return financeiro.registrar_estorno(comanda_id, **dados.model_dump(),
        chave_idempotencia=chave, db=db, usuario=usuario, filial_id=filial_id)


@router.post('/{comanda_id}/fechamento-financeiro', response_model=FechamentoFinanceiroOut,
             summary='Fechar financeiramente comanda quitada')
def fechar(comanda_id: UUID, dados: FechamentoFinanceiroCreate, chave: Chave, db: Banco,
           usuario: Ator, filial_id: UUID | None = None):
    """Exige conclusão operacional e saldo zero. Total zero exige motivo auditável."""
    return financeiro.fechar_comanda(comanda_id, **dados.model_dump(),
        chave_idempotencia=chave, db=db, usuario=usuario, filial_id=filial_id)
