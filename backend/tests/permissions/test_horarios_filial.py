"""Expediente via HTTP e ORM SQLite em memória; não acessa .env nem Supabase."""
import asyncio
from datetime import datetime, time
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from test_filiais import unidades, http_app, request


def semana(**changes):
    return {'dias': [dict(dia_semana=d, fechado=False, hora_inicio='08:00',
                          hora_fim='18:00', **changes) for d in range(7)]}


def enviar(app, s, body=None, role='admin', filial=None, method='PUT'):
    from app.core.security import criar_token
    return asyncio.run(request(app, f'/filiais/{(filial or s.a).id}/horarios',
                              criar_token(s.users[role].id), method, body))


@pytest.mark.parametrize('change', [
    {'dia_semana': -1}, {'dia_semana': 7}, {'dia_semana': True},
    {'hora_inicio': None}, {'hora_fim': None},
    {'hora_inicio': '18:00'}, {'hora_inicio': '19:00'},
    {'hora_inicio': '08:00+03:00'}, {'fechado': True}, {'fechado': 'false'},
])
def test_intervalos_invalidos(isolated_runtime, change):
    from app.schemas.horario_filial import DiaHorario
    with pytest.raises(ValidationError):
        DiaHorario(**(semana()['dias'][0] | change))


@pytest.mark.parametrize('count', [0, 6, 8])
def test_semana_exige_sete_dias(isolated_runtime, count):
    from app.schemas.horario_filial import HorariosFilialUpdate
    with pytest.raises(ValidationError):
        HorariosFilialUpdate(dias=[semana()['dias'][0]] * count)


def test_repeticao_e_campos_extras(isolated_runtime):
    from app.schemas.horario_filial import HorariosFilialUpdate
    body = semana()
    body['dias'][6]['dia_semana'] = 0
    with pytest.raises(ValidationError):
        HorariosFilialUpdate(**body)
    with pytest.raises(ValidationError):
        HorariosFilialUpdate(**semana(), filial_id=uuid4())


@pytest.mark.parametrize('role', ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_http_leitura_e_escrita_por_perfil(http_app, unidades, role):
    s = unidades
    code, result = enviar(http_app, s, role=role, method='GET')
    assert code == 200 and result == {'filial_id': str(s.a.id), 'configurado': False, 'dias': []}
    code, result = enviar(http_app, s, semana(), role=role)
    assert code == (200 if role == 'admin' else 403)
    if role == 'admin':
        assert result['configurado'] and [d['dia_semana'] for d in result['dias']] == list(range(7))


def test_escopo_atividade_revogacao_e_inexistente(http_app, unidades):
    s = unidades
    assert enviar(http_app, s, role='recepcao', filial=s.b, method='GET')[0] == 403
    s.b.ativa = False
    s.db.commit()
    assert enviar(http_app, s, semana(), filial=s.b)[0] == 403
    from types import SimpleNamespace
    assert enviar(http_app, s, semana(), filial=SimpleNamespace(id=uuid4()))[0] == 404
    # Perfil relido mesmo com instância antiga na identity map.
    from app.services.horarios_filial import atualizar
    from app.schemas.horario_filial import HorariosFilialUpdate
    from app.services.errors import SemPermissao
    admin = s.users['admin']
    s.db.execute(text("UPDATE usuarios SET perfil='BARBEIRO' WHERE id=:id"), {'id': admin.id.hex})
    s.db.commit()
    with pytest.raises(SemPermissao):
        atualizar(s.db, admin, s.a.id, HorariosFilialUpdate(**semana()))


def test_http_sem_autenticacao_e_validacao(http_app, unidades):
    s = unidades
    assert asyncio.run(request(http_app, f'/filiais/{s.a.id}/horarios', 'invalido'))[0] == 401
    body = semana()
    body['dias'].pop()
    assert enviar(http_app, s, body)[0] == 422


@pytest.mark.parametrize('status,expected', [('pendente', 409), ('aguardando', 409),
                                             ('cancelado', 200), ('concluido', 200),
                                             ('em_atendimento', 200)])
def test_fechamento_conflitante_preserva_reservas_e_comandas(http_app, unidades, status, expected):
    from app.models import Agendamento, Comanda, FilialHorario
    s = unidades
    assert enviar(http_app, s, semana())[0] == 200
    for reserva in s.db.scalars(select(Agendamento).where(Agendamento.filial_id == s.a.id)):
        reserva.status = status
    s.db.commit()
    antes = [(c.id, c.status, c.valor_total) for c in s.db.scalars(select(Comanda))]
    body = {'dias': [dict(dia_semana=d, fechado=True) for d in range(7)]}
    assert enviar(http_app, s, body)[0] == expected
    assert [(c.id, c.status, c.valor_total) for c in s.db.scalars(select(Comanda))] == antes
    assert all(h.fechado == (expected == 200) for h in s.db.scalars(select(FilialHorario)))


def test_primeira_configuracao_conflitante_nao_grava(http_app, unidades):
    from app.models import FilialHorario
    s = unidades
    body = {'dias': [dict(dia_semana=d, fechado=True) for d in range(7)]}
    assert enviar(http_app, s, body)[0] == 409
    assert s.db.scalars(select(FilialHorario)).all() == []


def test_atualizacao_falha_reverte_semana_inteira(unidades):
    from app.models import FilialHorario
    from app.schemas.horario_filial import HorariosFilialUpdate
    from app.services.horarios_filial import atualizar
    from app.services.persistencia import FalhaPersistencia
    s = unidades
    atualizar(s.db, s.users['admin'], s.a.id, HorariosFilialUpdate(**semana()))
    def falhar(session):
        session.flush()
        raise IntegrityError('ficticio', {}, Exception('falha simulada'))
    event.listen(s.db, 'before_commit', falhar)
    body = semana()
    body['dias'][0]['hora_fim'] = '20:00'
    try:
        with pytest.raises(FalhaPersistencia):
            atualizar(s.db, s.users['admin'], s.a.id, HorariosFilialUpdate(**body))
    finally:
        event.remove(s.db, 'before_commit', falhar)
    horarios = s.db.scalars(select(FilialHorario)).all()
    assert len(horarios) == 7 and all(h.hora_fim == time(18) for h in horarios)


def test_validacao_no_agendamento_e_isolamento(http_app, unidades):
    from app.models import Agendamento, Comanda
    from app.services.agendamento import criar_agendamento
    from app.services.errors import HorarioAgendamentoInvalido
    s = unidades
    assert enviar(http_app, s, semana())[0] == 200
    antes = (s.db.query(Agendamento).count(), s.db.query(Comanda).count())
    for inicio in ('07:59', '17:31'):
        with pytest.raises(HorarioAgendamentoInvalido):
            criar_agendamento(s.payload(hora=inicio), s.db, s.users['admin'])
    assert (s.db.query(Agendamento).count(), s.db.query(Comanda).count()) == antes
    from app.core.security import criar_token
    body_agenda = s.payload(hora='19:00').model_dump(mode='json')
    assert asyncio.run(request(http_app, '/agendamentos', criar_token(s.users['admin'].id),
                              'POST', body_agenda))[0] == 422
    for inicio in ('08:00', '17:30'):
        criar_agendamento(s.payload(hora=inicio), s.db, s.users['admin'])
    # B não configurada continua aceitando o horário legado.
    criar_agendamento(s.payload('outro', s.b, '19:00'), s.db, s.users['admin'])
    # Configuração distinta de B não altera A.
    body = semana()
    body['dias'][0] = {'dia_semana': 0, 'fechado': True}
    assert enviar(http_app, s, body, filial=s.b)[0] == 409  # reserva 19h fora do novo limite
    body = semana()
    for item in body['dias']:
        item['hora_fim'] = '21:00'
    assert enviar(http_app, s, body, filial=s.b)[0] == 200
    assert enviar(http_app, s, method='GET')[1]['dias'][0]['hora_fim'] == '18:00:00'
    assert enviar(http_app, s, filial=s.b, method='GET')[1]['dias'][0]['hora_fim'] == '21:00:00'


def test_semana_diferente_por_dia(http_app, unidades):
    from app.services.horarios_filial import validar_agendamento
    from app.services.errors import HorarioAgendamentoInvalido
    from datetime import timedelta
    s = unidades
    body = semana()
    reserva_data = s.payload().data
    fechado = (reserva_data.weekday() + 1) % 7
    body['dias'][fechado] = {'dia_semana': fechado, 'fechado': True}
    assert enviar(http_app, s, body)[0] == 200
    dia_fechado = reserva_data + timedelta(days=1)
    with pytest.raises(HorarioAgendamentoInvalido):
        validar_agendamento(s.db, s.a.id, dia_fechado, time(9), time(10))
    validar_agendamento(s.db, s.a.id, reserva_data, time(9), time(10))


def test_constraint_unicidade_e_fk(unidades):
    from app.models import FilialHorario
    s = unidades
    s.db.add(FilialHorario(filial_id=s.a.id, dia_semana=0, fechado=True))
    s.db.commit()
    for filial in (s.a.id, uuid4()):
        with pytest.raises(IntegrityError):
            s.db.add(FilialHorario(filial_id=filial, dia_semana=0, fechado=True))
            s.db.commit()
        s.db.rollback()


def test_dia_fechado_e_configuracao_incompleta(unidades):
    from app.models import FilialHorario
    from app.services.horarios_filial import validar_agendamento, consultar
    from app.services.errors import HorarioAgendamentoInvalido, ConflitoGestaoFilial
    s = unidades
    dia = s.payload().data
    s.db.add(FilialHorario(filial_id=s.a.id, dia_semana=dia.weekday(), fechado=True))
    s.db.commit()
    with pytest.raises(ConflitoGestaoFilial):
        consultar(s.db, s.users['admin'], s.a.id)
    with pytest.raises(HorarioAgendamentoInvalido):
        validar_agendamento(s.db, s.a.id, dia, time(9), time(10))
    for d in range(7):
        if d != dia.weekday():
            s.db.add(FilialHorario(filial_id=s.a.id, dia_semana=d, fechado=True))
    s.db.commit()
    with pytest.raises(HorarioAgendamentoInvalido):
        validar_agendamento(s.db, s.a.id, dia, time(9), time(10))


def test_reserva_vencida_nao_impede_e_atual_nao_pode_ser_cortada(http_app, unidades, monkeypatch):
    from app.services import agendamento
    s = unidades
    dia = s.payload().data
    body = {'dias': [dict(dia_semana=d, fechado=True) for d in range(7)]}
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime.combine(dia, time(9, 15), agendamento.FUSO_BARBEARIA))
    assert enviar(http_app, s, body)[0] == 409
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime.combine(dia, time(12), agendamento.FUSO_BARBEARIA))
    assert enviar(http_app, s, body)[0] == 200


@pytest.mark.parametrize('changes', [
    {'dia_semana': 7}, {'fechado': True, 'hora_inicio': time(8), 'hora_fim': time(18)},
    {'fechado': False, 'hora_inicio': None, 'hora_fim': None},
    {'fechado': False, 'hora_inicio': time(18), 'hora_fim': time(8)},
])
def test_constraints_reais_sqlite(unidades, changes):
    from app.models import FilialHorario
    s = unidades
    with pytest.raises(IntegrityError):
        s.db.add(FilialHorario(**({'filial_id': s.a.id, 'dia_semana': 0, 'fechado': True} | changes)))
        s.db.commit()
    s.db.rollback()
