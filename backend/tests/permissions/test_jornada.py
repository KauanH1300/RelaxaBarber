import asyncio
import pytest
from pydantic import ValidationError
from sqlalchemy import select, event
from sqlalchemy.exc import IntegrityError
from test_filiais import unidades, http_app, request


def semana():
    return {'dias': [dict(dia_semana=d, fechado=False, hora_inicio='08:00', hora_fim='18:00',
                          intervalos=[dict(dia_semana=d, fechado=False, hora_inicio='12:00', hora_fim='13:00')])
                     for d in range(7)], 'excecoes': []}


def enviar(app, s, body=None, role='admin', method='PUT', filial=None, alvo='barbeiro', suffix='jornada'):
    from app.core.security import criar_token
    return asyncio.run(request(app, f'/filiais/{(filial or s.a).id}/barbeiros/{s.users[alvo].id}/{suffix}',
                              criar_token(s.users[role].id), method, body))


@pytest.mark.parametrize('role', ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_perfis(http_app, unidades, role):
    for method, body in [('GET', None), ('PUT', semana())]:
        assert enviar(http_app, unidades, body, role, method)[0] == (200 if role == 'admin' else 403)


def test_folga_intervalo_excecao_e_reservas(http_app, unidades):
    from app.services.agendamento import criar_agendamento
    from app.services.errors import HorarioAgendamentoInvalido
    from app.models import JornadaBarbeiro, Agendamento
    s = unidades
    assert enviar(http_app, s, semana())[0] == 200
    for hora in ['07:59', '11:45', '12:30', '17:45']:
        with pytest.raises(HorarioAgendamentoInvalido):
            criar_agendamento(s.payload(hora=hora), s.db, s.users['admin'])
    for hora in ['11:30', '13:00', '17:30']:
        criar_agendamento(s.payload(hora=hora), s.db, s.users['admin'])
    antes = s.db.scalar(select(JornadaBarbeiro)).configuracao
    body = semana()
    dia = s.payload().data
    body['excecoes'] = [dict(data=str(dia), dia_semana=dia.weekday(), fechado=True)]
    assert enviar(http_app, s, body)[0] == 409
    assert s.db.scalar(select(JornadaBarbeiro)).configuracao == antes
    for r in s.db.scalars(select(Agendamento).where(Agendamento.barbeiro_id == s.users['barbeiro'].id)):
        r.status = 'cancelado'
    s.db.commit()
    assert enviar(http_app, s, body)[0] == 200
    with pytest.raises(HorarioAgendamentoInvalido):
        criar_agendamento(s.payload(hora='15:00'), s.db, s.users['admin'])


def test_disponibilidade_intersecao_e_outra_filial(http_app, unidades):
    from app.services.horarios_filial import atualizar
    from app.schemas.horario_filial import HorariosFilialUpdate
    s = unidades
    assert enviar(http_app, s, semana(), alvo='itinerante')[0] == 200
    body = semana()
    for d in body['dias']:
        d.pop('intervalos'); d['hora_fim'] = '16:00'
    atualizar(s.db, s.users['admin'], s.a.id, HorariosFilialUpdate(dias=body['dias']))
    suffix = f'disponibilidade?data={s.payload().data}&duracao=30'
    code, result = enviar(http_app, s, method='GET', alvo='itinerante', suffix=suffix)
    assert code == 200
    assert '08:00' in result['horarios'] and '15:30' in result['horarios']
    for hora in ['09:00', '10:00', '11:45', '12:00', '15:45', '16:00']:
        assert hora not in result['horarios']
    assert enviar(http_app, s, method='GET', role='barbeiro', alvo='itinerante', suffix=suffix)[0] == 403
    assert enviar(http_app, s, method='GET', role='recepcao', filial=s.b, alvo='outro', suffix=suffix)[0] == 403
    assert enviar(http_app, s, semana(), filial=s.b)[0] == 403  # alvo sem vínculo
    assert enviar(http_app, s, method='GET', filial=s.b, alvo='itinerante')[1]['configurado'] is False


@pytest.mark.parametrize('change', ['duplicado', 'fora', 'sobreposto', 'fechado', 'fuso', 'semana'])
def test_validacao(isolated_runtime, change):
    from app.schemas.jornada import JornadaUpdate
    body = semana(); dia = body['dias'][0]
    if change == 'duplicado':
        body['excecoes'] = [dict(data='2099-01-01', dia_semana=3, fechado=True)] * 2
    elif change == 'fora': dia['intervalos'][0]['hora_inicio'] = '07:00'
    elif change == 'sobreposto': dia['intervalos'] *= 2
    elif change == 'fechado': dia.update(fechado=True, hora_inicio=None, hora_fim=None)
    elif change == 'fuso': dia['intervalos'][0]['hora_inicio'] = '12:00+03:00'
    else: body['dias'].pop()
    with pytest.raises(ValidationError): JornadaUpdate(**body)


def test_rollback_integral(unidades):
    from app.services.jornada import atualizar, configuracao
    from app.schemas.jornada import JornadaUpdate
    from app.services.persistencia import FalhaPersistencia
    s = unidades
    atualizar(s.db, s.users['admin'], s.a.id, s.users['barbeiro'].id, JornadaUpdate(**semana()))
    antes = configuracao(s.db, s.a.id, s.users['barbeiro'].id)
    def falhar(session):
        session.flush()
        raise IntegrityError('simulado', {}, Exception('falha local'))
    body = semana(); body['dias'][0]['hora_fim'] = '20:00'
    event.listen(s.db, 'before_commit', falhar)
    try:
        with pytest.raises(FalhaPersistencia):
            atualizar(s.db, s.users['admin'], s.a.id, s.users['barbeiro'].id, JornadaUpdate(**body))
    finally:
        event.remove(s.db, 'before_commit', falhar)
    assert configuracao(s.db, s.a.id, s.users['barbeiro'].id) == antes
