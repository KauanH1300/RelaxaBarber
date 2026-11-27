from app.core.senhas import SenhaEquipe

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool

from app.schemas.portal_cliente import ConfirmarPortal, Entrada




class NovaSenhaEquipe(ConfirmarPortal):
    senha: SenhaEquipe


class TrocarSenhaEquipe(Entrada):
    senha_atual: str = Field(min_length=1, max_length=128)
    senha: SenhaEquipe

class RecuperacaoAdministrativa(Entrada):
    senha_atual_admin: str = Field(min_length=1, max_length=128)
    senha: SenhaEquipe
    motivo: str = Field(min_length=10, max_length=250, pattern=r'^\S.*\S$')


class VerificarLoginAdmin(Entrada):
    codigo: str = Field(pattern=r'^[0-9]{6}$')
    confiar: StrictBool = False


class DispositivoConfiavelOut(BaseModel):
    id: UUID
    criado_em: datetime
    expira_em: datetime
    atual: bool
