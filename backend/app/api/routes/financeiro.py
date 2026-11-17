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
    PagamentoCreate, PagamentoOut, RecebimentosCreate, EstornoCreate, EstornoOut,
    FechamentoFinanceiroCreate, FechamentoFinanceiroOut, ResumoFinanceiroOut,
    ErroFinanceiroOut, ErroValidacaoFinanceiraOut, ErroAutenticacaoFinanceiraOut,
)
from app.services import financeiro
from app.schemas.financeiro import HabilitacaoFinanceiraCreate, HabilitacaoFinanceiraOut
from app.services.habilitacao_financeira import habilitar

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


@router.post('/{comanda_id}/habilitacao-financeira', response_model=HabilitacaoFinanceiraOut,
             summary='Habilitar comanda de reserva publica apos conferencia administrativa')
def habilitar_portal(comanda_id: UUID, dados: HabilitacaoFinanceiraCreate, chave: Chave,
                    db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return habilitar(comanda_id, **dados.model_dump(), chave_idempotencia=chave,
                     db=db, usuario=usuario, filial_id=filial_id)


@router.get('/{comanda_id}/financeiro', response_model=ResumoFinanceiroOut,
            summary='Consultar situação financeira da comanda')
def consultar(comanda_id: UUID, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    """Resumo e histórico persistido; barbeiros consultam somente próprias comandas.

    Histórico ordenado por registrado_em e id, crescentes, em cada lista.
    Legado retorna saldo null e listas vazias. GET não faz commit ou mutação.
    """
    return financeiro.consultar_situacao(comanda_id, db, usuario, filial_id)


@router.post('/{comanda_id}/pagamentos', response_model=PagamentoOut,
             summary='Recuperar pagamento histórico idempotente', deprecated=True)
def pagar(comanda_id: UUID, dados: PagamentoCreate, chave: Chave, db: Banco,
          usuario: Ator, filial_id: UUID | None = None):
    """Somente replay de lançamento existente: 200; payload divergente: 409.

    Novos lançamentos nesta rota são rejeitados. Use recebimentos.
    """
    return financeiro.registrar_pagamento(comanda_id, **dados.model_dump(),
        chave_idempotencia=chave, db=db, usuario=usuario, filial_id=filial_id)


@router.post('/{comanda_id}/recebimentos', response_model=list[PagamentoOut],
             summary='Registrar recebimentos confirmados e fechar automaticamente ao quitar')
def receber(comanda_id: UUID, dados: RecebimentosCreate, chave: Chave, db: Banco,
            usuario: Ator, filial_id: UUID | None = None):
    """Parciais mantêm aberta; quitação e fechamento usam uma única transação.

    Não aceita intenções, QR Codes ou promessas. Replay retorna os recibos
    originais; consulte GET financeiro para o saldo e estado atuais.
    """
    return financeiro.registrar_recebimentos(comanda_id, **dados.model_dump(),
        chave_idempotencia=chave, db=db, usuario=usuario, filial_id=filial_id)


@router.post('/{comanda_id}/estornos', response_model=EstornoOut,
             summary='Registrar ou recuperar estorno idempotente (ADMIN)')
def estornar(comanda_id: UUID, dados: EstornoCreate, chave: Chave, db: Banco,
             usuario: Ator, filial_id: UUID | None = None):
    """Somente ADMIN. Motivo obrigatório; sem exceder o pagamento ou antecedê-lo."""
    return financeiro.registrar_estorno(comanda_id, **dados.model_dump(),
        chave_idempotencia=chave, db=db, usuario=usuario, filial_id=filial_id)


@router.post('/{comanda_id}/fechamento-financeiro', response_model=FechamentoFinanceiroOut,
             summary='Confirmar pagamento integral e fechar comanda atomicamente')
def fechar(comanda_id: UUID, dados: FechamentoFinanceiroCreate, chave: Chave, db: Banco,
           usuario: Ator, filial_id: UUID | None = None):
    """Novos pagamentos exigem atendimento iniciado ou concluído e soma exata do saldo.

    Lista vazia permite finalizar quitação histórica. Total zero exige fluxo próprio.
    Um commit registra pagamentos, fechamento e estado/data da nova comanda.
    """
    return financeiro.fechar_comanda(comanda_id, **dados.model_dump(),
        chave_idempotencia=chave, db=db, usuario=usuario, filial_id=filial_id)
