"""PostgreSQL descartável: locks, exclusão global, CASCADE e auditoria."""
from conftest import versao_agendamento
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Event
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.orm import Session
from test_contexto_filiais import duas_filiais, payload
from test_concorrencia import data
from test_cancelamento_etapa_g import wait_for_lock
from test_horarios_filial import preparar, semana


@pytest.fixture
def reserva(runtime_pg, duas_filiais):
    from app.models import Usuario
    from app.services.agendamento import criar_agendamento
    with Session(runtime_pg) as db:
        r = criar_agendamento(payload(duas_filiais, duas_filiais['filial']), db, db.get(Usuario, duas_filiais['admin']))
        return duas_filiais | {'reserva': r.id, 'versao': r.atualizado_em}


def mover(db, s, hora='11:00', barbeiro=None):
    from app.models import Usuario
    from app.schemas.reagendamento import ReagendamentoUpdate
    from app.services.reagendamento import reagendar
    return reagendar(s['reserva'], ReagendamentoUpdate(data=date(2099, 1, 1), hora_inicio=hora,
        barbeiro_id=barbeiro or s['user'], atualizado_em_esperado=s['versao']), db, db.get(Usuario, s['admin']))


@pytest.mark.parametrize('primeira', ['cancelamento', 'reagendamento'])
def test_pr59_cancelamento_concorrente_com_reagendamento(runtime_pg, reserva, primeira):
    from app.models import Usuario, Agendamento, Reagendamento
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    s = reserva
    def cancelar(db):
        return atualizar_status(s['reserva'], AgendamentoStatusUpdate(status='cancelado', motivo_cancelamento='Desistência',
            confirmado=True, atualizado_em_esperado=s['versao']), db, db.get(Usuario, s['admin']))
    mover_reserva = lambda db: mover(db, s)
    assert corrida(runtime_pg, cancelar if primeira == 'cancelamento' else mover_reserva,
                   mover_reserva if primeira == 'cancelamento' else cancelar) == 'ConflitoEstadoAgendamento'
    with Session(runtime_pg) as db:
        a = db.get(Agendamento, s['reserva'])
        assert (a.status == 'cancelado') == (primeira == 'cancelamento')
        assert db.query(Reagendamento).count() == int(primeira == 'reagendamento')


def corrida(engine, primeira, segunda, rollback=False):
    from app.services.errors import AgendamentoInvalido, ConflitoEstadoAgendamento, ConflitoGestaoFilial, HorarioAgendamentoInvalido, HorarioOcupado
    from app.services.persistencia import FalhaPersistencia
    pronto, liberar, iniciou = Event(), Event(), Event()
    pids = {}
    class Pausada(Session):
        def commit(self):
            self.flush(); pronto.set()
            assert liberar.wait(10)
            if rollback: raise IntegrityError('simulado', {}, Exception('rollback local'))
            return super().commit()
    def executar(op, primeiro=False):
        with (Pausada if primeiro else Session)(engine, autoflush=False) as db:
            pids[primeiro] = preparar(db)
            if not primeiro: iniciou.set()
            try:
                op(db)
                return 'ok'
            except (AgendamentoInvalido, ConflitoEstadoAgendamento, ConflitoGestaoFilial, HorarioAgendamentoInvalido, HorarioOcupado, FalhaPersistencia) as exc:
                assert db.scalar(text('SELECT 1')) == 1
                return 'rollback' if primeiro and rollback else type(exc).__name__
    with ThreadPoolExecutor(max_workers=2) as pool:
        um = pool.submit(executar, primeira, True)
        try:
            assert pronto.wait(10)
            dois = pool.submit(executar, segunda)
            assert iniciou.wait(10)
            wait_for_lock(engine, pids[False])
            with engine.connect() as conn:
                assert pids[True] in conn.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid': pids[False]})
        finally: liberar.set()
        assert um.result(timeout=15) == ('rollback' if rollback else 'ok')
        return dois.result(timeout=15)


@pytest.mark.parametrize('rollback', [False, True])
def test_duas_alteracoes_mesma_versao(runtime_pg, reserva, rollback):
    from app.models import Reagendamento, Agendamento, Comanda
    s = reserva
    resultado = corrida(runtime_pg, lambda db: mover(db, s, barbeiro=s['other']),
                        lambda db: mover(db, s, '12:00'), rollback)
    assert resultado == ('ok' if rollback else 'ConflitoEstadoAgendamento')
    with Session(runtime_pg) as db:
        r = db.get(Agendamento, s['reserva'])
        c = db.scalar(select(Comanda).where(Comanda.agendamento_id == r.id))
        assert r.barbeiro_id == c.barbeiro_id == (s['user'] if rollback else s['other'])
        assert r.hora_inicio == time(12 if rollback else 11)
        assert db.query(Reagendamento).count() == 1


@pytest.mark.parametrize('mover_primeiro', [False, True])
@pytest.mark.parametrize('rollback', [False, True])
def test_criacao_e_reagendamento_disputam_slot_global(runtime_pg, reserva, mover_primeiro, rollback):
    from app.models import Usuario, Reagendamento, Agendamento
    from app.schemas.agendamento import AgendamentoCreate
    from app.services.agendamento import criar_agendamento
    s = reserva
    def criar(db):
        body = AgendamentoCreate(**(payload(s, s['second']).model_dump() | {'hora_inicio': time(11)}))
        criar_agendamento(body, db, db.get(Usuario, s['admin']))
    move = lambda db: mover(db, s)
    resultado = corrida(runtime_pg, move if mover_primeiro else criar, criar if mover_primeiro else move, rollback)
    assert resultado == ('ok' if rollback else 'ConflitoPersistencia')
    with Session(runtime_pg) as db:
        assert db.query(Agendamento).count() == (1 if mover_primeiro != rollback else 2)
        assert db.query(Reagendamento).count() == int(mover_primeiro != rollback)


@pytest.mark.parametrize('tipo', ['filial', 'jornada'])
@pytest.mark.parametrize('gestao_primeiro', [False, True])
def test_expediente_ou_jornada_serializa_com_reagendamento(runtime_pg, reserva, tipo, gestao_primeiro):
    from app.models import Usuario
    from app.services import horarios_filial, jornada
    from app.schemas.jornada import JornadaUpdate
    s = reserva
    def configurar(db):
        ator = db.get(Usuario, s['admin'])
        if tipo == 'filial': horarios_filial.atualizar(db, ator, s['filial'], semana(fim='10:00'))
        else: jornada.atualizar(db, ator, s['filial'], s['user'], JornadaUpdate.model_validate(semana(fim='10:00').model_dump()))
    move = lambda db: mover(db, s)
    result = corrida(runtime_pg, configurar if gestao_primeiro else move, move if gestao_primeiro else configurar)
    assert result == ('HorarioAgendamentoInvalido' if gestao_primeiro else 'ConflitoGestaoFilial')


@pytest.mark.parametrize('status', ['cancelado', 'em_atendimento'])
def test_estado_relido_apos_lock(runtime_pg, reserva, status):
    from app.models import Usuario
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s = reserva
    if status == 'em_atendimento':
        with Session(runtime_pg) as db:
            r = atualizar_status(s['reserva'], AgendamentoStatusUpdate(status='aguardando'), db, db.get(Usuario, s['admin']))
            s = s | {'versao': r.atualizado_em}
    def atualizar(db):
        atualizar_status(s['reserva'], AgendamentoStatusUpdate(status=status, confirmado=True, atualizado_em_esperado=versao_agendamento(db, s['reserva']), motivo_cancelamento=('Cancelamento fictício conferido' if status == 'cancelado' else None)), db, db.get(Usuario, s['admin']))
    assert corrida(runtime_pg, atualizar, lambda db: mover(db, s)) == 'ConflitoEstadoAgendamento'


def test_auditoria_imutavel_acl_e_downgrade(pg, runtime_pg, reserva):
    from app.models import Reagendamento
    from test_modelagem_filiais import scripts
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    with Session(runtime_pg) as db:
        mover(db, reserva)
        assert db.query(Reagendamento).count() == 1
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT has_table_privilege('relaxabarber_runtime','public.reagendamentos','SELECT')"))
        assert not conn.scalar(text("SELECT has_table_privilege('relaxabarber_runtime','public.reagendamentos','DELETE')"))
        for role in ('anon', 'authenticated', 'service_role'):
            assert not conn.scalar(text("SELECT has_table_privilege(:role,'public.reagendamentos','SELECT')"), {'role': role})
    for sql in ['UPDATE public.reagendamentos SET motivo=motivo', 'DELETE FROM public.reagendamentos', 'TRUNCATE public.reagendamentos']:
        with pytest.raises(DBAPIError):
            with pg.begin() as conn: conn.execute(text(sql))
    with pytest.raises(DBAPIError, match='historico'):
        with pg.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                scripts().get_revision('c54e18f920a7').module.downgrade()
