"""PostgreSQL real: constraints, espera entre transações e atomicidade ORM."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier, Event
from uuid import uuid4

import pytest
from sqlalchemy import text, select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def data(pg):
    from app.models import Usuario, PerfilEnum, Cliente, Servico
    with Session(pg) as db:
        user = Usuario(nome='Teste', email='teste@example.test', senha_hash='ficticio', perfil=PerfilEnum.BARBEIRO)
        other = Usuario(nome='Outro', email='outro@example.test', senha_hash='ficticio', perfil=PerfilEnum.BARBEIRO)
        client = Cliente(nome='Cliente fictício', telefone='00000000000')
        service = Servico(nome='Corte', preco=30, tempo_estimado=30, comissao_padrao=10)
        db.add_all([user, other, client, service]); db.commit()
        return dict(user=user.id, other=other.id, client=client.id, service=service.id)


def insert(conn, data, start='09:00', end='09:30', status='pendente', professional=None, day='2099-01-01'):
    ident = uuid4()
    conn.execute(text('''INSERT INTO public.agendamentos
        (id, cliente_id, barbeiro_id, data, hora_inicio, hora_fim, status, origem)
        VALUES (:id, :client, :professional, :day, :start, :end, :status, 'recepcao')'''),
        dict(id=ident, client=data['client'], professional=professional or data['user'],
             day=day, start=start, end=end, status=status))
    return ident


@pytest.mark.parametrize('status', ['pendente', 'aguardando', 'em_atendimento', 'concluido'])
def test_status_ativos_bloqueiam(pg, data, status):
    with pg.begin() as conn:
        insert(conn, data, status=status)
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            insert(conn, data, start='09:15', end='09:45')
    assert error.value.orig.pgcode == '23P01'
    assert error.value.orig.diag.constraint_name == 'ex_agendamentos_profissional_periodo'


@pytest.mark.parametrize('change', [dict(start='09:30', end='10:00'), dict(day='2099-01-02'), dict(status='cancelado'), dict(professional='other')])
def test_intervalos_permitidos(pg, data, change):
    change = dict(change)
    if change.get('professional') == 'other':
        change['professional'] = data['other']
    with pg.begin() as conn:
        insert(conn, data)
        insert(conn, data, **change)


@pytest.mark.parametrize('end', ['09:00', '08:59', '00:00'])
def test_intervalo_invalido(pg, data, end):
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            # Cancelado também precisa respeitar CHECK; não constrói o range.
            insert(conn, data, end=end, status='cancelado')
    assert error.value.orig.pgcode == '23514'


@pytest.mark.parametrize('confirm', [True, False])
def test_conexao_independente_aguarda_resultado_da_primeira(pg, data, confirm):
    started, finished = Event(), Event()
    backend_pid = []
    def competitor():
        try:
            with pg.begin() as conn:
                conn.execute(text("SET LOCAL statement_timeout = '8s'"))
                backend_pid.append(conn.scalar(text('SELECT pg_backend_pid()')))
                started.set()
                insert(conn, data)
            return 'confirmed'
        except IntegrityError as error:
            assert error.orig.pgcode == '23P01'
            return 'conflict'
        finally:
            finished.set()
    with pg.connect() as first, ThreadPoolExecutor(max_workers=1) as pool:
        transaction = first.begin()
        insert(first, data)
        future = pool.submit(competitor)
        try:
            assert started.wait(3)
            # Observa espera de lock no servidor, não apenas atraso do executor.
            from time import monotonic
            deadline = monotonic() + 3
            waiting = False
            with pg.connect() as observer:
                while monotonic() < deadline:
                    waiting = observer.scalar(text("SELECT wait_event_type = 'Lock' FROM pg_stat_activity WHERE pid=:pid"), {'pid':backend_pid[0]})
                    observer.rollback()
                    if waiting:
                        break
                    assert not finished.wait(.02)
            assert waiting
        finally:
            transaction.commit() if confirm else transaction.rollback()
        assert future.result(timeout=10) == ('conflict' if confirm else 'confirmed')


def test_servico_concorrente_atomico_e_sessoes_recuperadas(pg, data):
    from app.models import Usuario, Agendamento, AgendamentoServico, Comanda, ItemComanda
    from app.schemas.agendamento import AgendamentoCreate
    from app.services.agendamento import criar_agendamento
    from app.services.persistencia import ConflitoPersistencia
    barrier = Barrier(2, timeout=5)
    class CoordinatedSession(Session):
        def flush(self, *args, **kwargs):
            if any(isinstance(obj, Agendamento) for obj in self.new):
                barrier.wait()  # ambos passaram pela consulta; antes do INSERT
            return super().flush(*args, **kwargs)
    def create():
        with CoordinatedSession(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout = '10s'"))
            pid = db.scalar(text('SELECT pg_backend_pid()'))
            payload = AgendamentoCreate(cliente_id=data['client'], barbeiro_id=data['user'], data=date(2099,1,1), hora_inicio=time(9), servicos=[{'servico_id':data['service']}])
            try:
                criar_agendamento(payload, db, db.get(Usuario, data['user']))
                result = 'confirmed'
            except ConflitoPersistencia as error:
                assert error.mensagem == 'Barbeiro já tem agendamento nesse horário'
                result = 'conflict'
            assert db.scalar(text('SELECT 1')) == 1
            return result, pid
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))
    assert sorted(value for value, _ in results) == ['confirmed', 'conflict']
    assert len({pid for _, pid in results}) == 2
    with Session(pg) as db:
        for model in (Agendamento, AgendamentoServico, Comanda, ItemComanda):
            assert db.scalar(select(func.count()).select_from(model)) == 1


@pytest.mark.parametrize('confirm', [True, False])
def test_cancelamento_so_libera_apos_commit(pg, data, confirm):
    with pg.begin() as conn:
        ident = insert(conn, data)
    with pg.connect() as conn:
        transaction = conn.begin()
        conn.execute(text("UPDATE public.agendamentos SET status='cancelado' WHERE id=:id"), {'id':ident})
        transaction.commit() if confirm else transaction.rollback()
    if confirm:
        with pg.begin() as conn:
            insert(conn, data)
    else:
        with pytest.raises(IntegrityError):
            with pg.begin() as conn:
                insert(conn, data)


def test_downgrade_preserva_extensao_e_reupgrade(pg, data):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    module = migration_module()
    with pg.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.downgrade()
            assert conn.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='btree_gist'")) == 1
            module.upgrade()
    test_status_ativos_bloqueiam(pg, data, 'pendente')


def migration_module():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/f62b18d4a903_protege_intervalos_agendamentos.py'
    spec = importlib.util.spec_from_file_location('migration_f', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('invalid', [False, True])
def test_migration_recusa_dados_preexistentes_sem_corrigir(pg, data, invalid):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    migration = migration_module()
    with pg.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        insert(conn, data)
        insert(conn, data, end='09:00' if invalid else '09:30')
    with pytest.raises(IntegrityError):
        with pg.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.agendamentos')) == 2
        assert conn.scalar(text("SELECT count(*) FROM pg_constraint WHERE conname='ex_agendamentos_profissional_periodo'")) == 0


def test_extensao_em_outro_schema(pg, data):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    migration = migration_module()
    with pg.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
            conn.execute(text('CREATE SCHEMA IF NOT EXISTS extensions'))
            conn.execute(text('ALTER EXTENSION btree_gist SET SCHEMA extensions'))
            migration.upgrade()
    test_status_ativos_bloqueiam(pg, data, 'pendente')


@pytest.mark.parametrize('operation', ['reactivate', 'move'])
def test_updates_tambem_respeitam_exclusao(pg, data, operation):
    with pg.begin() as conn:
        insert(conn, data)
        ident = insert(conn, data, status='cancelado') if operation == 'reactivate' else insert(conn, data, start='10:00', end='10:30')
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            conn.execute(text("UPDATE public.agendamentos SET status='pendente', hora_inicio='09:00', hora_fim='09:30' WHERE id=:id"), {'id':ident})
    assert error.value.orig.pgcode == '23P01'
