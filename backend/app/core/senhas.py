"""Política para novas senhas. Nunca aplicada à autenticação de senhas existentes."""
from functools import lru_cache
from pathlib import Path
from typing import Annotated
from pydantic import AfterValidator, Field


@lru_cache(maxsize=1)
def bloqueadas():
    arquivo = Path(__file__).with_name("senhas_comuns.txt")
    return frozenset(linha.casefold() for linha in arquivo.read_text(encoding="utf-8").splitlines() if linha)


def validar_nova_senha(valor: str) -> str:
    if valor.casefold() in bloqueadas():
        raise ValueError("Esta senha é comum ou previsível. Escolha outra senha ou uma frase mais longa.")
    return valor


SenhaCliente = Annotated[str, Field(min_length=8, max_length=128), AfterValidator(validar_nova_senha)]
SenhaEquipe = Annotated[str, Field(min_length=15, max_length=128), AfterValidator(validar_nova_senha)]
