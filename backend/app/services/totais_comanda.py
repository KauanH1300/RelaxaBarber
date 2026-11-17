"""Cálculo único: benefícios por linha, centavos e desconto geral."""
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import and_, case, func, or_
from app.models.comanda import Comanda, ItemComanda

ZERO = Decimal('0.00')
CENTAVO = Decimal('0.01')


def desconto(base, tipo='nenhum', valor=ZERO):
    valor = Decimal(valor)
    if not base.is_finite() or base < ZERO or not valor.is_finite() or valor < ZERO:
        raise ValueError('Base ou desconto inválido')
    if tipo not in ('nenhum', 'valor', 'percentual', 'cortesia'):
        raise ValueError('Tipo de desconto inválido')
    if tipo in ('nenhum', 'cortesia') and valor != ZERO:
        raise ValueError('Nenhum/cortesia não aceita valor adicional')
    if tipo == 'percentual' and valor > 100:
        raise ValueError('Percentual excede 100%')
    abatimento = (base if tipo == 'cortesia' else valor if tipo == 'valor' else
                  (base * valor / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP) if tipo == 'percentual' else ZERO)
    if abatimento > base:
        raise ValueError('Desconto excede a base disponível; revise o benefício antes de reduzir os itens')
    return abatimento


def subtotal_item(item):
    bruto = item.quantidade * item.preco_unitario
    return bruto - desconto(bruto, getattr(item, 'desconto_tipo', 'nenhum'), getattr(item, 'desconto_valor', ZERO))


def total_itens(itens):
    return sum((subtotal_item(i) for i in itens if i.ativo), ZERO)


def resumo_totais(itens, tipo='nenhum', valor=ZERO):
    ativos = [i for i in itens if i.ativo]
    bruto = sum((i.quantidade * i.preco_unitario for i in ativos), ZERO)
    subtotal = total_itens(ativos)
    geral = desconto(subtotal, tipo, valor)
    return dict(total_bruto=bruto, desconto_itens=bruto-subtotal, subtotal=subtotal,
                desconto_geral=geral, total=subtotal-geral)


def sql_desconto(base, tipo, valor):
    return case((tipo == 'cortesia', base), (tipo == 'valor', valor),
                (tipo == 'percentual', func.round(base * valor / 100, 2)), else_=ZERO)


def sql_invalido(base, tipo, valor, cortesia=False):
    return or_(base < 0, valor < 0, valor > Decimal('99999999.99'),
        tipo.notin_(('nenhum', 'valor', 'percentual', 'cortesia') if cortesia else ('nenhum', 'valor', 'percentual')),
        and_(tipo == 'percentual', valor > 100),
        and_(tipo.in_(('nenhum', 'cortesia')), valor != 0),
        sql_desconto(base, tipo, valor) > base)


def consulta_totais(db):
    bruto = ItemComanda.quantidade * ItemComanda.preco_unitario
    liquido = bruto - sql_desconto(bruto, ItemComanda.desconto_tipo, ItemComanda.desconto_valor)
    bases = db.query(ItemComanda.comanda_id.label('id'), func.sum(liquido).label('subtotal'),
        func.sum(case((or_(ItemComanda.quantidade <= 0, ItemComanda.preco_unitario < 0,
            sql_invalido(bruto, ItemComanda.desconto_tipo, ItemComanda.desconto_valor, True)), 1), else_=0)).label('invalidos'),
    ).filter(ItemComanda.ativo.is_(True)).group_by(ItemComanda.comanda_id).subquery()
    base = func.coalesce(bases.c.subtotal, ZERO)
    return db.query(Comanda.id.label('id'),
        (base-sql_desconto(base, Comanda.desconto_tipo, Comanda.desconto_valor)).label('total'),
        (func.coalesce(bases.c.invalidos, 0)+case((sql_invalido(base, Comanda.desconto_tipo, Comanda.desconto_valor), 1), else_=0)).label('invalidos'),
    ).outerjoin(bases, bases.c.id == Comanda.id)
