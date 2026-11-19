"""Rateio determinístico de centavos para bases e liberação de comissões."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID
from app.services.totais_comanda import desconto, subtotal_item

CENTAVO = Decimal('0.01')
ZERO = Decimal('0.00')

@dataclass(frozen=True)
class ComissaoCalculada:
    item_id: UUID
    base: Decimal
    percentual: Decimal
    gerada: Decimal
    liberada: Decimal


def _centavos(valor):
    return int((valor / CENTAVO).to_integral_exact())


def ratear(total: Decimal, pesos: dict[UUID, Decimal]) -> dict[UUID, Decimal]:
    """Distribui centavos por maiores restos; desempate estável pelo UUID."""
    if total < 0 or any(p < 0 for p in pesos.values()):
        raise ValueError('Rateio não aceita valores negativos')
    soma = sum(pesos.values(), ZERO)
    if not soma:
        if total: raise ValueError('Não é possível ratear sem base')
        return {chave: ZERO for chave in pesos}
    unidades = _centavos(total)
    partes = {chave: Decimal(unidades) * peso / soma for chave, peso in pesos.items()}
    inteiros = {chave: int(valor) for chave, valor in partes.items()}
    sobram = unidades - sum(inteiros.values())
    ordem = sorted(pesos, key=lambda chave: (-(partes[chave] - inteiros[chave]), str(chave)))
    for chave in ordem[:sobram]: inteiros[chave] += 1
    return {chave: Decimal(valor) * CENTAVO for chave, valor in inteiros.items()}


def calcular(itens, desconto_tipo, desconto_valor, percentuais, recebido_liquido):
    """Rateia descontos e recebimentos entre itens com comissão identificada."""
    ativos = [item for item in itens if item.ativo]
    subtotais = {item.id: subtotal_item(item) for item in ativos}
    subtotal = sum(subtotais.values(), ZERO)
    desconto_geral = desconto(subtotal, desconto_tipo, desconto_valor)
    total = subtotal - desconto_geral
    if recebido_liquido < ZERO or recebido_liquido > total:
        raise ValueError('Recebimento incompatível com o total')
    abatimentos = ratear(desconto_geral, subtotais)
    resultados = []
    for item in sorted(ativos, key=lambda i: str(i.id)):
        if item.id not in percentuais or not (item.tipo == 'servico' or (item.tipo == 'produto' and getattr(item, 'produto_id', None) is not None)): continue
        percentual = Decimal(percentuais[item.id])
        if not percentual.is_finite() or not ZERO <= percentual <= 100:
            raise ValueError('Percentual inv\u00e1lido')
        base = subtotais[item.id] - abatimentos[item.id]
        gerada = (base * percentual / 100).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        resultados.append((item.id, base, percentual, gerada))
    total_gerado = sum((r[3] for r in resultados), ZERO)
    total_liberado = ((total_gerado * recebido_liquido / total).quantize(CENTAVO, rounding=ROUND_HALF_UP)
                       if total else ZERO)
    liberacoes = ratear(total_liberado, {r[0]:r[3] for r in resultados})
    return tuple(ComissaoCalculada(ident, base, percentual, gerada, liberacoes[ident])
                 for ident, base, percentual, gerada in resultados)
