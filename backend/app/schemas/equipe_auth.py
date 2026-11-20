from typing import Annotated

from pydantic import Field

from app.schemas.portal_cliente import ConfirmarPortal, Entrada

SenhaEquipe = Annotated[str, Field(min_length=8, max_length=128)]


class NovaSenhaEquipe(ConfirmarPortal):
    senha: SenhaEquipe


class TrocarSenhaEquipe(Entrada):
    senha_atual: str = Field(min_length=1, max_length=128)
    senha: SenhaEquipe
