"""Cálculo puro de saldos para fechamento de comissões.

Os eventos existentes são saldos cumulativos, não lançamentos de crédito.
O chamador deve fornecer o último evento confirmado de cada item e todas as
parcelas já congeladas do profissional na filial, inclusive de outros períodos.
Esta função não persiste dados nem decide autorizações ou concorrência.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID

ZERO = Decimal('0.00')
CENTAVO = Decimal('0.01')


def _valor(valor: Decimal) -> Decimal:
    try:
        numero = Decimal(valor)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Valor monetário inválido') from None
    try:
        invalido = not numero.is_finite() or numero < ZERO or numero != numero.quantize(CENTAVO)
    except InvalidOperation:
        invalido = True
    if invalido:
        raise ValueError('Valor deve ser não negativo e ter no máximo dois decimais')
    return numero


@dataclass(frozen=True)
class ComissaoAtual:
    item_id: UUID
    evento_id: UUID
    origem: date
    gerada: Decimal
    liberada: Decimal


@dataclass(frozen=True)
class EventoAcumulado:
    item_id: UUID
    evento_id: UUID
    profissional_id: UUID
    filial_id: UUID
    ordem: int
    origem: date
    gerada: Decimal
    liberada: Decimal


def estados_atuais(eventos: list[EventoAcumulado], profissional_id: UUID,
                   filial_id: UUID) -> list[ComissaoAtual]:
    """Seleciona o último estado do item antes de filtrar o profissional.

    Filtrar o profissional antes do último evento ressuscitaria saldos de
    profissionais anteriores após uma transferência. O chamador deve ler
    todos os eventos dos itens incluídos na filial, sob a mesma transação.
    """
    ultimos: dict[UUID, EventoAcumulado] = {}
    ordens: set[int] = set()
    for evento in eventos:
        if evento.filial_id != filial_id or evento.ordem in ordens or evento.ordem <= 0:
            raise ValueError('Contexto ou ordem de eventos inconsistentes')
        ordens.add(evento.ordem)
        anterior = ultimos.get(evento.item_id)
        if anterior is None or anterior.ordem < evento.ordem:
            ultimos[evento.item_id] = evento
    return [ComissaoAtual(e.item_id, e.evento_id, e.origem, e.gerada, e.liberada)
            for e in ultimos.values() if e.profissional_id == profissional_id]


@dataclass(frozen=True)
class ParcelaCongelada:
    id: UUID
    item_id: UUID
    ordem: int
    valor: Decimal
    pago_liquido: Decimal


@dataclass(frozen=True)
class SaldoParcela:
    parcela_id: UUID
    congelado: Decimal
    pago_liquido: Decimal
    disponivel: Decimal
    ajuste_negativo: Decimal


@dataclass(frozen=True)
class Demonstrativo:
    gerada: Decimal
    liberada: Decimal
    pendente_recebimento: Decimal
    elegivel_periodo: Decimal
    credito_por_item: dict[UUID, Decimal]
    parcelas: tuple[SaldoParcela, ...]
    deficit_pago: Decimal
    bloqueio_por_deficit: bool


def demonstrar(atuais: list[ComissaoAtual], parcelas: list[ParcelaCongelada],
               inicio: date, fim: date) -> Demonstrativo:
    """Calcula créditos por origem e saldos seguros após ajustes negativos.

    O período usa a data de origem, mesmo quando a liberação ocorreu depois.
    Repasses líquidos devem ser atribuídos às parcelas no ato do pagamento e
    reduzidos, sem excluir o lançamento original, em estornos administrativos.
    Débito causado por pagamentos já realizados bloqueia novos repasses e
    fechamentos até ser compensado fora deste cálculo.
    """
    if inicio > fim:
        raise ValueError('Intervalo de datas inválido')
    por_item: dict[UUID, ComissaoAtual] = {}
    for item in atuais:
        gerada, liberada = _valor(item.gerada), _valor(item.liberada)
        if item.item_id in por_item or liberada > gerada:
            raise ValueError('Estado atual de comissão inconsistente')
        por_item[item.item_id] = item

    grupos: dict[UUID, list[ParcelaCongelada]] = {}
    ids: set[UUID] = set()
    for parcela in parcelas:
        valor, pago = _valor(parcela.valor), _valor(parcela.pago_liquido)
        if parcela.id in ids or parcela.item_id not in por_item or pago > valor:
            raise ValueError('Parcela de comissão inconsistente')
        ids.add(parcela.id)
        grupos.setdefault(parcela.item_id, []).append(parcela)

    creditos: dict[UUID, Decimal] = {}
    saldos: list[SaldoParcela] = []
    deficit = ZERO
    for item_id, item in por_item.items():
        congeladas = sorted(grupos.get(item_id, []), key=lambda p: (p.ordem, str(p.id)))
        total_congelado = sum((_valor(p.valor) for p in congeladas), ZERO)
        total_pago = sum((_valor(p.pago_liquido) for p in congeladas), ZERO)
        liberada = _valor(item.liberada)
        deficit += max(ZERO, total_pago - liberada)
        limite = max(ZERO, liberada - total_pago)
        for parcela in congeladas:
            restante = _valor(parcela.valor) - _valor(parcela.pago_liquido)
            disponivel = min(restante, limite)
            limite -= disponivel
            saldos.append(SaldoParcela(parcela.id, _valor(parcela.valor),
                _valor(parcela.pago_liquido), disponivel, restante - disponivel))
        if inicio <= item.origem <= fim:
            creditos[item_id] = max(ZERO, liberada - total_congelado)

    if deficit:
        creditos = {ident: ZERO for ident in creditos}
        saldos = [SaldoParcela(p.parcela_id, p.congelado, p.pago_liquido,
                    ZERO, p.ajuste_negativo) for p in saldos]
    no_periodo = [i for i in por_item.values() if inicio <= i.origem <= fim]
    gerada = sum((_valor(i.gerada) for i in no_periodo), ZERO)
    liberada = sum((_valor(i.liberada) for i in no_periodo), ZERO)
    return Demonstrativo(gerada, liberada, gerada - liberada,
        sum(creditos.values(), ZERO), creditos, tuple(saldos), deficit, deficit > ZERO)
