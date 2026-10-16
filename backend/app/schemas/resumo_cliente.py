"""Contratos de leitura. Dinheiro indisponível é null, nunca zero ou comanda."""
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AtendimentosFilial(BaseModel):
    filial_id: UUID
    filial_nome: str
    atendimentos_concluidos: int = Field(ge=0)


class ResumoCliente(BaseModel):
    cliente_id: UUID
    escopo_filiais: Literal['empresa', 'filiais_autorizadas']
    escopo_profissional: Literal['todos', 'proprio']
    parcial: bool
    atendimentos_concluidos: int = Field(ge=0)
    filiais: list[AtendimentosFilial]


class FinanceiroFilial(AtendimentosFilial):
    total_gasto: Decimal | None = Field(default=None, ge=0, description='Gasto efetivamente pago, em BRL; null enquanto indisponível.')


class ResumoFinanceiroCliente(ResumoCliente):
    financeiro_disponivel: Literal[False] = False
    total_gasto: Decimal | None = Field(default=None, ge=0, description='Gasto efetivamente pago no escopo informado, em BRL; null enquanto indisponível.')
    filiais: list[FinanceiroFilial]

    @model_validator(mode='after')
    def sem_valores_sem_pagamentos(self):
        if self.total_gasto is not None or any(f.total_gasto is not None for f in self.filiais):
            raise ValueError('Valores financeiros indisponíveis precisam ser null')
        return self
