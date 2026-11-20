from datetime import date, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class ItemAtendimento(BaseModel):
    nome: str
    quantidade: int


class InsumoAtendimento(BaseModel):
    nome: str
    unidade: str
    quantidade: Decimal


class AtendimentoCliente(BaseModel):
    id: UUID
    data: date
    hora_inicio: time
    profissional: str
    status: Literal['concluido', 'cancelado', 'nao_compareceu']
    servicos: list[ItemAtendimento]
    produtos: list[ItemAtendimento]
    insumos: list[InsumoAtendimento]
    observacoes: str | None


class AtendimentoClientePago(AtendimentoCliente):
    total_pago_liquido: Decimal


class PaginaAtendimentos(BaseModel):
    atendimentos: list[AtendimentoClientePago | AtendimentoCliente]
    proxima_pagina: int | None
