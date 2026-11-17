"""Definição única dos itens que compõem o total financeiro atual."""
from decimal import Decimal
from sqlalchemy import case, func, or_
from app.models.comanda import ItemComanda


def total_itens(itens):
    return sum((i.quantidade * i.preco_unitario for i in itens if i.ativo), Decimal('0.00'))


def consulta_totais(db):
    return db.query(ItemComanda.comanda_id.label('id'),
        func.sum(ItemComanda.quantidade * ItemComanda.preco_unitario).label('total'),
        func.sum(case((or_(ItemComanda.quantidade <= 0, ItemComanda.preco_unitario < 0), 1), else_=0)).label('invalidos'),
    ).filter(ItemComanda.ativo.is_(True)).group_by(ItemComanda.comanda_id)
