"""Limites da aplicação compatíveis com as colunas PostgreSQL existentes."""
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BeforeValidator, Field

PRECO_MAXIMO = Decimal("99999999.99")
DURACAO_MAXIMA = 480


def validar_preco(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Preço deve ser um valor monetário")
    try:
        price = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Preço deve ser um valor monetário") from None
    if not price.is_finite():
        raise ValueError("Preço deve ser finito")
    if not Decimal("0") <= price <= PRECO_MAXIMO:
        raise ValueError("Preço deve estar entre 0 e 99999999.99")
    if price.as_tuple().exponent < -2:
        raise ValueError("Preço deve ter no máximo duas casas decimais")
    return price


def validar_duracao(value: object) -> int:
    if type(value) is not int or not 1 <= value <= DURACAO_MAXIMA:
        raise ValueError("Duração deve ser um número inteiro entre 1 e 480 minutos")
    return value


def validar_comissao(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("Comissão deve ser um percentual")
    try:
        percentual = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Comissão deve ser um percentual") from None
    if not percentual.is_finite():
        raise ValueError("Comissão deve ser finita")
    if not Decimal("0") <= percentual <= Decimal("100"):
        raise ValueError("Comissão deve estar entre 0 e 100")
    if percentual.as_tuple().exponent < -2:
        raise ValueError("Comissão deve ter no máximo duas casas decimais")
    return percentual


Preco = Annotated[
    Decimal, BeforeValidator(validar_preco),
    Field(ge=0, le=PRECO_MAXIMO, max_digits=10, decimal_places=2, allow_inf_nan=False),
]
Duracao = Annotated[int, BeforeValidator(validar_duracao), Field(ge=1, le=DURACAO_MAXIMA)]
Comissao = Annotated[
    Decimal, BeforeValidator(validar_comissao),
    Field(ge=0, le=100, max_digits=5, decimal_places=2, allow_inf_nan=False),
]
