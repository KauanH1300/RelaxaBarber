from sqlalchemy import select, or_, and_, delete
from app.models import JornadaBarbeiro, Agendamento, PerfilEnum
from app.schemas.jornada import JornadaUpdate
from app.services import filiais, horarios_filial
from app.services.gestao_filiais import _filial_exclusiva
from app.services.persistencia import transacao_escrita
from app.services.errors import SemPermissao, ConflitoGestaoFilial, HorarioAgendamentoInvalido


def configuracao(db, filial_id, barbeiro_id):
    rows = list(db.scalars(select(JornadaBarbeiro).where(
        JornadaBarbeiro.filial_id == filial_id, JornadaBarbeiro.barbeiro_id == barbeiro_id,
    ).execution_options(populate_existing=True)))
    return JornadaUpdate.model_validate(rows[0].configuracao) if rows else None


def comporta(config, data, inicio, fim):
    if config is None:
        return True
    dia = next((e for e in config.excecoes if e.data == data), None)
    if dia is None:
        dia = next(d for d in config.dias if d.dia_semana == data.weekday())
    return (horarios_filial._comporta(dia, inicio, fim) and
            not any(inicio < i.hora_fim and fim > i.hora_inicio for i in dia.intervalos))


def validar_agendamento(db, filial_id, barbeiro_id, data, inicio, fim):
    if not comporta(configuracao(db, filial_id, barbeiro_id), data, inicio, fim):
        raise HorarioAgendamentoInvalido('Atendimento fora da jornada do barbeiro, em folga ou intervalo')


def consultar(db, usuario, filial_id, barbeiro_id):
    usuario = filiais.usuario_atual(db, usuario)
    if usuario.perfil != PerfilEnum.ADMIN:
        raise SemPermissao('Somente ADMIN pode consultar a configuração da jornada')
    filiais.resolver_filial(db, usuario, filial_id)
    filiais.validar_profissional(db, barbeiro_id, filial_id)
    config = configuracao(db, filial_id, barbeiro_id)
    return dict(filial_id=filial_id, barbeiro_id=barbeiro_id, configurado=config is not None,
                dias=config.dias if config else [], excecoes=config.excecoes if config else [])


def atualizar(db, usuario, filial_id, barbeiro_id, dados):
    from app.services.agendamento import agora_local
    with transacao_escrita(db):
        # Mesma linha/ordem de locks do expediente, inclusive na primeira configuração.
        filial = _filial_exclusiva(db, usuario, filial_id)
        filiais.resolver_filial(db, usuario, filial.id, bloquear=True)
        filiais.validar_profissional(db, barbeiro_id, filial.id)
        agora = agora_local()
        reservas = db.scalars(select(Agendamento).where(
            Agendamento.filial_id == filial.id, Agendamento.barbeiro_id == barbeiro_id,
            Agendamento.status.in_(('pendente', 'aguardando', 'em_atendimento')),
            or_(Agendamento.data > agora.date(), and_(Agendamento.data == agora.date(),
                Agendamento.hora_fim > agora.time().replace(tzinfo=None))),
        ).execution_options(populate_existing=True)).all()
        for reserva in reservas:
            if not comporta(dados, reserva.data, reserva.hora_inicio, reserva.hora_fim):
                raise ConflitoGestaoFilial(f'Jornada incompatível com a reserva {reserva.id} em {reserva.data}')
        db.execute(delete(JornadaBarbeiro).where(JornadaBarbeiro.filial_id == filial.id,
                                               JornadaBarbeiro.barbeiro_id == barbeiro_id))
        db.add(JornadaBarbeiro(filial_id=filial.id, barbeiro_id=barbeiro_id,
                              configuracao=dados.model_dump(mode='json')))
        resultado = dict(filial_id=filial.id, barbeiro_id=barbeiro_id, configurado=True,
                         dias=dados.dias, excecoes=dados.excecoes)
    return resultado


def disponibilidade(db, usuario, filial_id, barbeiro_id, data, duracao):
    from datetime import datetime, timedelta
    from app.services.agendamento import agora_local
    from app.services.permissoes_agendamento import escopo_consulta
    usuario = filiais.usuario_atual(db, usuario)
    filiais.resolver_filial(db, usuario, filial_id)
    escopo_consulta(usuario, barbeiro_id)
    filiais.validar_profissional(db, barbeiro_id, filial_id)
    config = configuracao(db, filial_id, barbeiro_id)
    dias_filial = horarios_filial._dias(db, filial_id)
    if dias_filial and {d.dia_semana for d in dias_filial} != set(range(7)):
        raise ConflitoGestaoFilial('Expediente da filial incompleto')
    dia_filial = next((d for d in dias_filial if d.dia_semana == data.weekday()), None)
    reservas = list(db.scalars(select(Agendamento).where(
        Agendamento.barbeiro_id == barbeiro_id, Agendamento.data == data,
        Agendamento.status != 'cancelado')))
    agora = agora_local().replace(tzinfo=None)
    inicio = datetime.combine(data, datetime.min.time())
    horarios = []
    for minuto in range(0, 1440, 15):
        if minuto + duracao >= 1440:
            continue
        a = inicio + timedelta(minutes=minuto)
        b = a + timedelta(minutes=duracao)
        if a < agora or b.date() != data or not comporta(config, data, a.time(), b.time()):
            continue
        if dia_filial is not None and not horarios_filial._comporta(dia_filial, a.time(), b.time()):
            continue
        if not any(a.time() < r.hora_fim and b.time() > r.hora_inicio for r in reservas):
            horarios.append(a.strftime('%H:%M'))
    return dict(data=data, duracao=duracao, horarios=horarios)
