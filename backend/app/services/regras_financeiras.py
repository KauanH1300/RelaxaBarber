"""Validação e canonicalização sem banco; não recebe totais do cliente."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.financeiro_errors import EntradaFinanceiraInvalida

FUSO = ZoneInfo("America/Recife")
LIMITE = Decimal("99999999.99")
CENTAVO = Decimal("0.01")
FORMAS = ("dinheiro", "pix", "debito", "credito")


def valor_monetario(valor: Decimal, *, permitir_zero=False) -> Decimal:
    if not isinstance(valor, Decimal):
        raise EntradaFinanceiraInvalida("Informe valor Decimal, sem float")
    try:
        valido = (valor.is_finite() and 0 <= valor <= LIMITE
                  and valor == valor.quantize(CENTAVO) and (permitir_zero or valor > 0))
    except InvalidOperation:
        valido = False
    if not valido:
        raise EntradaFinanceiraInvalida("Valor fora da faixa ou com fração de centavo")
    return valor.quantize(CENTAVO)


def identificador(valor) -> UUID:
    if not isinstance(valor, UUID):
        raise EntradaFinanceiraInvalida("Informe identificador UUID válido")
    return valor


def data_efetiva(valor) -> datetime:
    try:
        if not isinstance(valor, datetime) or valor.tzinfo is None or valor.utcoffset() is None:
            raise EntradaFinanceiraInvalida("Data efetiva exige timestamp com timezone")
        return valor.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise EntradaFinanceiraInvalida("Data efetiva inválida") from exc


def validar_janela(efetiva: datetime, agora: datetime, *, admin: bool) -> None:
    # Comparar instantes UTC garante 168 horas, inclusive em transições de fuso.
    # O relógio do serviço é apresentado em America/Recife, nunca no fuso do cliente.
    efetiva = data_efetiva(efetiva)
    agora = data_efetiva(agora)
    if efetiva > agora:
        raise EntradaFinanceiraInvalida("Data efetiva não pode estar no futuro")
    if not admin and efetiva < agora - timedelta(days=7):
        raise EntradaFinanceiraInvalida("Lançamento anterior a sete dias exige ADMIN")


def motivo_auditavel(valor, *, obrigatorio=False):
    if valor is None and not obrigatorio:
        return None
    if not isinstance(valor, str) or not valor.strip():
        raise EntradaFinanceiraInvalida("Informe um motivo auditável")
    return valor.strip()


def fingerprint(operacao: str, **payload) -> str:
    """Payload já validado; valores/datas/UUIDs têm representação canônica."""
    def canonico(valor):
        if isinstance(valor, Decimal):
            return format(valor.quantize(CENTAVO), ".2f")
        if isinstance(valor, datetime):
            return data_efetiva(valor).isoformat(timespec="microseconds")
        if isinstance(valor, UUID):
            return str(valor)
        return valor
    dados = {"operacao": operacao, **{chave: canonico(valor) for chave, valor in payload.items()}}
    return sha256(json.dumps(dados, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
