"""Concorrência real somente no PostgreSQL descartável validado pela fixture pg."""
from concurrent.futures import ThreadPoolExecutor
from datetime import time
from threading import Event

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_contexto_filiais import duas_filiais, payload
from test_concorrencia import data
from test_cancelamento_etapa_g import wait_for_lock


@pytest.fixture
def horarios_pg(runtime_pg):
    """Os nove cenários conectam efetivamente com o login restrito."""
    return runtime_pg


def semana(fechado=False, fim='18:00'):
    from app.schemas.horario_filial import HorariosFilialUpdate
    return HorariosFilialUpdate(dias=[{'dia_semana': d, 'fechado': True} if fechado else
        {'dia_semana': d, 'fechado': False, 'hora_inicio': '08:00', 'hora_fim': fim}
        for d in range(7)])


def configurar(db, s, dados, filial=None):
    from app.models import Usuario
    from app.services.horarios_filial import atualizar
    return atualizar(db, db.get(Usuario, s['admin']), filial or s['filial'], dados)


def reservar(db, s, filial=None):
    from app.models import Usuario
    from app.services.agendamento import criar_agendamento
    return criar_agendamento(payload(s, filial or s['filial']), db, db.get(Usuario, s['user']))


def conferir_semana(engine, filial, *, fechado=False, fim=time(18)):
    from app.models import FilialHorario
    with Session(engine) as db:
        rows = db.scalars(select(FilialHorario).where(FilialHorario.filial_id == filial)
                          .order_by(FilialHorario.dia_semana)).all()
        assert [r.dia_semana for r in rows] == list(range(7))
        assert all(r.fechado == fechado for r in rows)
        assert all((r.hora_inicio, r.hora_fim) ==
                   ((None, None) if fechado else (time(8), fim)) for r in rows)


def conferir_reservas(engine, total):
    from app.models import Agendamento, AgendamentoServico, Comanda, ItemComanda
    with Session(engine) as db:
        for model in (Agendamento, AgendamentoServico, Comanda, ItemComanda):
            assert db.query(model).count() == total
        if total:
            reserva, comanda = db.scalar(select(Agendamento)), db.scalar(select(Comanda))
            assert comanda.agendamento_id == reserva.id
            assert comanda.filial_id == reserva.filial_id
            assert comanda.valor_total == 30


def preparar(db):
    assert db.scalar(text('SHOW transaction_isolation')) == 'read committed'
    db.execute(text("SET LOCAL statement_timeout='12s'"))
    db.execute(text("SET LOCAL lock_timeout='8s'"))
    db.execute(text("SET LOCAL idle_in_transaction_session_timeout='20s'"))
    return db.scalar(text('SELECT pg_backend_pid()'))


def corrida(engine, primeira, segunda, *, rollback=False, bloqueia=True, durante=None):
    from app.services.errors import ConflitoGestaoFilial, HorarioAgendamentoInvalido
    from app.services.persistencia import FalhaPersistencia
    ready, release, started = Event(), Event(), Event()
    pids = {}

    class Paused(Session):
        def commit(self):
            self.flush()
            ready.set()
            assert release.wait(10), 'Primeira transação não recebeu liberação'
            if rollback:
                raise IntegrityError('teste local', {}, Exception('rollback induzido após flush'))
            return super().commit()

    def first():
        with Paused(engine, autoflush=False) as db:
            pids['first'] = preparar(db)
            try:
                primeira(db)
                return 'ok'
            except FalhaPersistencia:
                if not rollback:
                    raise
                assert db.scalar(text('SELECT 1')) == 1
                return 'rollback'

    def second():
        with Session(engine, autoflush=False) as db:
            pids['second'] = preparar(db)
            started.set()
            try:
                segunda(db)
                return 'ok'
            except (ConflitoGestaoFilial, HorarioAgendamentoInvalido) as exc:
                assert db.scalar(text('SELECT 1')) == 1
                return type(exc).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(first)
        try:
            assert ready.wait(10), 'Primeira transação não chegou ao commit'
            two = pool.submit(second)
            assert started.wait(10), 'Segunda transação não iniciou'
            assert pids['first'] != pids['second']
            if bloqueia:
                wait_for_lock(engine, pids['second'])
                with engine.connect() as conn:
                    assert pids['first'] in conn.scalar(text('SELECT pg_blocking_pids(:pid)'),
                                                       {'pid': pids['second']})
            else:
                # Deve terminar enquanto a primeira ainda está parada no evento.
                assert two.result(timeout=6) == 'ok'
                assert not one.done()
            if durante:
                durante()
        finally:
            release.set()
        assert one.result(timeout=15) == ('rollback' if rollback else 'ok')
        return two.result(timeout=15)


@pytest.mark.parametrize('gestao_primeiro', [True, False])
@pytest.mark.parametrize('rollback', [True, False])
def test_configuracao_e_criacao_serializam_na_filial(horarios_pg, duas_filiais, gestao_primeiro, rollback):
    engine, s = horarios_pg, duas_filiais
    with Session(engine) as db:
        configurar(db, s, semana())
    def gestao(db):
        configurar(db, s, semana(fechado=True))
    def reserva(db):
        reservar(db, s)
    resultado = corrida(engine, gestao if gestao_primeiro else reserva,
                        reserva if gestao_primeiro else gestao, rollback=rollback)
    assert resultado == ('ok' if rollback else
                         'HorarioAgendamentoInvalido' if gestao_primeiro else 'ConflitoGestaoFilial')
    fechado = gestao_primeiro != rollback
    conferir_semana(engine, s['filial'], fechado=fechado)
    conferir_reservas(engine, 0 if fechado else 1)


@pytest.mark.parametrize('rollback', [True, False])
def test_duas_atualizacoes_preservam_semana_atomica(horarios_pg, duas_filiais, rollback):
    engine, s = horarios_pg, duas_filiais
    with Session(engine) as db:
        configurar(db, s, semana())
    assert corrida(engine, lambda db: configurar(db, s, semana(fim='19:00')),
                   lambda db: configurar(db, s, semana(fim='20:00')), rollback=rollback,
                   durante=lambda: conferir_semana(engine, s['filial'])) == 'ok'
    conferir_semana(engine, s['filial'], fim=time(20))
    conferir_reservas(engine, 0)


@pytest.mark.parametrize('segunda_gestao', [True, False])
def test_filiais_distintas_nao_esperam_lock_da_outra(horarios_pg, duas_filiais, segunda_gestao):
    engine, s = horarios_pg, duas_filiais
    with Session(engine) as db:
        configurar(db, s, semana())
        configurar(db, s, semana(), s['second'])
    segunda = (lambda db: configurar(db, s, semana(fim='20:00'), s['second'])) if segunda_gestao else (
        lambda db: reservar(db, s, s['second']))
    assert corrida(engine, lambda db: configurar(db, s, semana(fechado=True)),
                   segunda, bloqueia=False) == 'ok'
    conferir_semana(engine, s['filial'], fechado=True)
    conferir_semana(engine, s['second'], fim=time(20) if segunda_gestao else time(18))
    conferir_reservas(engine, 0 if segunda_gestao else 1)


def test_primeira_configuracao_revertida_nao_deixa_semana_parcial(horarios_pg, duas_filiais):
    from app.models import FilialHorario
    engine, s = horarios_pg, duas_filiais
    assert corrida(engine, lambda db: configurar(db, s, semana(fechado=True)),
                   lambda db: reservar(db, s), rollback=True) == 'ok'
    with Session(engine) as db:
        assert db.query(FilialHorario).count() == 0
    conferir_reservas(engine, 1)
