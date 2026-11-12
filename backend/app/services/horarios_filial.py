"""Semana completa por filial; ausência preserva o comportamento legado.

Criação de reservas mantém SHARE na filial. Alterações de expediente usam
UPDATE na mesma linha antes de conferir reservas e substituir os sete dias.
"""
from sqlalchemy import delete, select, or_, and_

from app.models import Agendamento, FilialHorario
from app.schemas.horario_filial import DiaHorario, HorariosFilialOut
from app.services import filiais
from app.services.gestao_filiais import _filial_exclusiva
from app.services.errors import ConflitoGestaoFilial, HorarioAgendamentoInvalido
from app.services.persistencia import transacao_escrita


def _dias(db, filial_id):
    return list(db.scalars(select(FilialHorario).where(
        FilialHorario.filial_id == filial_id,
    ).order_by(FilialHorario.dia_semana).execution_options(populate_existing=True)))


def consultar(db, usuario, filial_id):
    filial = filiais.resolver_filial(db, usuario, filial_id)
    dias = _dias(db, filial.id)
    if dias and {dia.dia_semana for dia in dias} != set(range(7)):
        raise ConflitoGestaoFilial('Expediente incompleto; solicite ao administrador salvar a semana completa')
    return HorariosFilialOut(filial_id=filial.id, configurado=bool(dias),
                            dias=[DiaHorario.model_validate(dia) for dia in dias])


def _comporta(dia, inicio, fim):
    return not dia.fechado and dia.hora_inicio <= inicio and fim <= dia.hora_fim


def validar_agendamento(db, filial_id, data, inicio, fim):
    # Chamador já autorizou e bloqueou a filial; nunca usar para autorizar acesso.
    dias = _dias(db, filial_id)
    if not dias:
        return
    if {dia.dia_semana for dia in dias} != set(range(7)):
        raise HorarioAgendamentoInvalido('Expediente da filial incompleto')
    dia = next(dia for dia in dias if dia.dia_semana == data.weekday())
    if not _comporta(dia, inicio, fim):
        raise HorarioAgendamentoInvalido('Atendimento fora do horário de funcionamento da filial')


def atualizar(db, usuario, filial_id, dados):
    from app.services.agendamento import agora_local

    with transacao_escrita(db):
        filial = _filial_exclusiva(db, usuario, filial_id)
        # Revalida atividade e acesso com a linha da filial já bloqueada.
        filiais.resolver_filial(db, usuario, filial.id, bloquear=True)
        agora = agora_local()
        reservas = db.scalars(select(Agendamento).where(
            Agendamento.filial_id == filial.id,
            Agendamento.status.in_(('pendente', 'aguardando')),
            or_(Agendamento.data > agora.date(), and_(
                Agendamento.data == agora.date(),
                Agendamento.hora_fim > agora.time().replace(tzinfo=None),
            )),
        ).execution_options(populate_existing=True)).all()
        semana = {dia.dia_semana: dia for dia in dados.dias}
        for reserva in reservas:
            if not _comporta(semana[reserva.data.weekday()], reserva.hora_inicio, reserva.hora_fim):
                raise ConflitoGestaoFilial(
                    f'Expediente incompatível com a reserva {reserva.id} em {reserva.data}'
                )
        db.execute(delete(FilialHorario).where(FilialHorario.filial_id == filial.id))
        db.add_all([FilialHorario(filial_id=filial.id, **dia.model_dump()) for dia in dados.dias])
        resultado = HorariosFilialOut(filial_id=filial.id, configurado=True,
                                     dias=sorted(dados.dias, key=lambda dia: dia.dia_semana))
    return resultado
