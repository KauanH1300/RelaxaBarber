from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FilialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    nome: str
    fuso_horario: str
    endereco: str | None = None
    agenda_publica: bool = False


class ConfiguracaoAgendaFilial(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    endereco: str | None = Field(default=None, max_length=300)
    agenda_publica: bool

    @model_validator(mode='after')
    def exigir_endereco(self):
        if self.agenda_publica and not self.endereco:
            raise ValueError('Informe o endereço antes de habilitar a agenda pública')
        return self


class VinculoUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ativo: bool


class UsuarioFilialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    usuario_id: UUID
    filial_id: UUID
    ativo: bool
