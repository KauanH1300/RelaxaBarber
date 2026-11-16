from datetime import date
from pydantic import Field, model_validator
from app.schemas.horario_filial import DiaHorario, HorariosFilialUpdate


class DiaJornada(DiaHorario):
    intervalos: list[DiaHorario] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def validar_intervalos(self):
        anterior = self.hora_inicio
        for i in self.intervalos:
            if self.fechado or i.fechado or i.hora_inicio is None:
                raise ValueError('Folgas não possuem intervalos')
            if not (anterior <= i.hora_inicio < i.hora_fim <= self.hora_fim):
                raise ValueError('Intervalos devem estar ordenados, dentro da jornada e sem sobreposição')
            anterior = i.hora_fim
        return self


class ExcecaoJornada(DiaJornada):
    data: date


class JornadaUpdate(HorariosFilialUpdate):
    dias: list[DiaJornada] = Field(min_length=7, max_length=7)
    excecoes: list[ExcecaoJornada] = Field(default_factory=list, max_length=366)

    @model_validator(mode='after')
    def validar_excecoes(self):
        if len({e.data for e in self.excecoes}) != len(self.excecoes):
            raise ValueError('Informe apenas uma exceção por data')
        if any(e.dia_semana != e.data.weekday() for e in self.excecoes):
            raise ValueError('Dia da semana incompatível com a data')
        return self
