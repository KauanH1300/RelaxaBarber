from datetime import date, datetime, time
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BloqueioCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    filial_id: UUID | None = None
    barbeiro_id: UUID
    data: date
    hora_inicio: time
    hora_fim: time
    motivo: str = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def validar_intervalo(self):
        if self.hora_inicio.tzinfo or self.hora_fim.tzinfo or self.hora_inicio >= self.hora_fim:
            raise ValueError('Informe um intervalo local válido dentro do mesmo dia')
        return self


class BloqueioOut(BloqueioCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filial_id: UUID
    criado_por: UUID
    criado_em: datetime


HorasAntecedencia = Annotated[int, Field(strict=True, ge=0, le=87600)]
DiasAntecedencia = Annotated[int, Field(strict=True, ge=1, le=3650)]


class AntecedenciaAgenda(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    antecedencia_reserva_horas: HorasAntecedencia
    antecedencia_maxima_reserva_dias: DiasAntecedencia | None
    antecedencia_cancelamento_horas: HorasAntecedencia

    @model_validator(mode='after')
    def validar_janela(self):
        dias = self.antecedencia_maxima_reserva_dias
        if dias is not None and self.antecedencia_reserva_horas >= dias * 24:
            raise ValueError('A antecedência máxima deve ser maior que a mínima para agendar')
        return self
