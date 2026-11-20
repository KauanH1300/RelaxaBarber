"""Contratos de leitura do histórico operacional e financeiro."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AtendimentosFilial(BaseModel):
    filial_id: UUID
    filial_nome: str
    atendimentos_concluidos: int = Field(ge=0)


class ResumoCliente(BaseModel):
    cliente_id: UUID
    escopo_filiais: Literal['empresa', 'filiais_autorizadas', 'filial']
    escopo_profissional: Literal['todos', 'proprio']
    parcial: bool
    atendimentos_concluidos: int = Field(ge=0)
    filiais: list[AtendimentosFilial]


class FinanceiroFilial(AtendimentosFilial):
    total_gasto: Decimal


class MovimentacaoCliente(BaseModel):
    comanda_id: UUID
    filial_id: UUID
    filial_nome: str
    tipo: Literal['agendada', 'avulsa']
    ultima_movimentacao_em: datetime
    recebido: Decimal
    estornado: Decimal
    total_gasto: Decimal


class ResumoFinanceiroCliente(ResumoCliente):
    financeiro_disponivel: Literal[True] = True
    total_gasto: Decimal
    filiais: list[FinanceiroFilial]
    movimentacoes: list[MovimentacaoCliente]
