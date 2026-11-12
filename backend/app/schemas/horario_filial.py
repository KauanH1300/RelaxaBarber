from datetime import time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from typing import Annotated


class DiaHorario(BaseModel):
    model_config = ConfigDict(extra='forbid', from_attributes=True)
    dia_semana: Annotated[int, Field(strict=True, ge=0, le=6)]
    fechado: StrictBool
    hora_inicio: time | None = None
    hora_fim: time | None = None

    @model_validator(mode='after')
    def validar_intervalo(self):
        if self.fechado:
            if self.hora_inicio is not None or self.hora_fim is not None:
                raise ValueError('Dia fechado não deve possuir horários')
        else:
            if self.hora_inicio is None or self.hora_fim is None:
                raise ValueError('Informe abertura e fechamento para o dia aberto')
            if self.hora_inicio.tzinfo is not None or self.hora_fim.tzinfo is not None:
                raise ValueError('Informe horários locais sem fuso')
            if self.hora_inicio >= self.hora_fim:
                raise ValueError('A abertura deve ser anterior ao fechamento no mesmo dia')
        return self


class HorariosFilialUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dias: list[DiaHorario] = Field(min_length=7, max_length=7)

    @model_validator(mode='after')
    def validar_semana(self):
        if {dia.dia_semana for dia in self.dias} != set(range(7)):
            raise ValueError('Informe os sete dias sem repetição (0=segunda, 6=domingo)')
        return self


class HorariosFilialOut(BaseModel):
    filial_id: UUID
    configurado: bool
    dias: list[DiaHorario]
