"""Concorrência de status com conexões e identity maps independentes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Event
from time import monotonic
from uuid import uuid4

import pytest
from sqlalchemy import text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def booking(pg):
    from app.models import Usuario, PerfilEnum, Cliente, Servico
    from app.schemas.agendamento import AgendamentoCreate, AgendamentoStatusUpdate
    from app.services.agendamento import criar_agendamento, atualizar_status
    with Session(pg, autoflush=False) as db:
        user=Usuario(nome='Profissional teste',email='g@example.test',senha_hash='ficticio',perfil=PerfilEnum.BARBEIRO)
        client=Cliente(nome='Fictício',telefone='00000000000')
        service=Servico(nome='Corte',preco=30,tempo_estimado=30,comissao_padrao=10)
        db.add_all([user,client,service]);db.commit()
        payload=AgendamentoCreate(cliente_id=client.id,barbeiro_id=user.id,data=date(2099,1,1),hora_inicio=time(9),servicos=[{'servico_id':service.id}])
        appointment=criar_agendamento(payload,db,user)
        atualizar_status(appointment.id,AgendamentoStatusUpdate(status='aguardando'),db,user)
        return appointment.id,user.id


def wait_for_lock(engine,pid):
    deadline=monotonic()+3
    with engine.connect() as conn:
        while monotonic()<deadline:
            waiting=conn.scalar(text("SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"),{'pid':pid})
            conn.rollback()
            if waiting:
                return
            Event().wait(.02)
    raise AssertionError('Conexão concorrente não aguardou lock')


@pytest.mark.parametrize('initial,first,second,expected', [
    ('aguardando','cancelado','em_atendimento',400),
    ('aguardando','em_atendimento','cancelado',409),
    ('aguardando','cancelado','cancelado',400),
    ('em_atendimento','concluido','cancelado',400),
    ('em_atendimento','concluido','concluido',400),
])
def test_status_concorrente_rele_estado_inclusive_identity_map(pg,booking,initial,first,second,expected):
    from app.models import Usuario,Agendamento,Comanda
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    from app.services.errors import AgendamentoInvalido,ConflitoEstadoAgendamento
    ident,user_id=booking
    if initial == 'em_atendimento':
        with Session(pg) as db:
            atualizar_status(ident,AgendamentoStatusUpdate(status=initial),db,db.get(Usuario,user_id))
    ready,go=Event(),Event()
    pid=[]
    def competing():
        with Session(pg,autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            stale=db.get(Agendamento,ident)
            command=db.scalar(select(Comanda).where(Comanda.agendamento_id==ident))
            assert stale.status==initial and command.status=='aberta'
            user=db.get(Usuario,user_id)
            pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            ready.set()
            assert go.wait(5)
            try:
                atualizar_status(ident,AgendamentoStatusUpdate(status=second),db,user)
            except ConflitoEstadoAgendamento:
                outcome=409
            except AgendamentoInvalido:
                outcome=400
            else:
                outcome=200
            assert db.scalar(text('SELECT 1'))==1
            return outcome,db.get(Agendamento,ident).status
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(competing)
        try:
            assert ready.wait(5)
            with Session(pg,autoflush=False) as db:
                db.execute(text("SET LOCAL statement_timeout='8s'"))
                actor_pid=db.scalar(text('SELECT pg_backend_pid()'))
                assert actor_pid != pid[0]
                db.scalar(select(Agendamento).where(Agendamento.id==ident).with_for_update())
                go.set()
                wait_for_lock(pg,pid[0])
                atualizar_status(ident,AgendamentoStatusUpdate(status=first,motivo_cancelamento='Solicitação' if first=='cancelado' else None),db,db.get(Usuario,user_id))
        finally:
            go.set()
        assert future.result(timeout=10)==(expected,first)
    with Session(pg) as db:
        appointment=db.get(Agendamento,ident)
        command=db.scalar(select(Comanda).where(Comanda.agendamento_id==ident))
        assert command.status=={'cancelado':'cancelada','em_atendimento':'aberta','concluido':'fechada'}[first]
        assert (command.data_fechamento is not None)==(first=='concluido')
        assert len(command.itens)==len(appointment.servicos)==1
        assert command.valor_total==30
        assert (appointment.cancelado_por==user_id)==(first=='cancelado')
        assert (appointment.cancelado_em is not None)==(first=='cancelado')


def test_comanda_rele_estado_apos_espera_do_lock(pg,booking):
    from app.models import Usuario,Agendamento,Comanda
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    from app.services.errors import ConflitoEstadoAgendamento
    ident,user_id=booking
    ready,go=Event(),Event();pid=[]
    def competing():
        with Session(pg,autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            appointment=db.get(Agendamento,ident)
            stale=db.scalar(select(Comanda).where(Comanda.agendamento_id==ident))
            assert stale.status=='aberta'
            user=db.get(Usuario,user_id)
            pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            ready.set();assert go.wait(5)
            with pytest.raises(ConflitoEstadoAgendamento):
                atualizar_status(ident,AgendamentoStatusUpdate(status='cancelado'),db,user)
            assert db.get(Agendamento,ident).status=='aguardando'
            assert db.get(Comanda,stale.id).status=='fechada'
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(competing)
        try:
            assert ready.wait(5)
            with pg.begin() as conn:
                conn.execute(text("UPDATE comandas SET status='fechada' WHERE agendamento_id=:id"),{'id':ident})
                go.set();wait_for_lock(pg,pid[0])
        finally:
            go.set()
        future.result(timeout=10)


def test_cancelamento_libera_intervalo_sem_excluir_historico(pg,booking):
    from app.models import Usuario,Agendamento,Comanda
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    ident,user_id=booking
    with Session(pg) as db:
        atualizar_status(ident,AgendamentoStatusUpdate(status='cancelado'),db,db.get(Usuario,user_id))
        original=db.get(Agendamento,ident)
        replacement=Agendamento(cliente_id=original.cliente_id,barbeiro_id=original.barbeiro_id,data=original.data,hora_inicio=original.hora_inicio,hora_fim=original.hora_fim,status='pendente',origem='recepcao')
        db.add(replacement);db.commit()
        assert db.get(Agendamento,ident).status=='cancelado'
        assert db.scalar(select(Comanda).where(Comanda.agendamento_id==ident)).status=='cancelada'


def test_migration_g_preserva_historico_e_fk(pg,booking):
    import importlib.util
    from pathlib import Path
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    path=Path(__file__).resolve().parents[1]/'alembic/versions/a73d92bc6e14_auditoria_cancelamento_agendamentos.py'
    spec=importlib.util.spec_from_file_location('migration_g',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    ident,_=booking
    with pg.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
            conn.execute(text("UPDATE agendamentos SET status='cancelado' WHERE id=:id"),{'id':ident})
            migration.upgrade()
        row=conn.execute(text('SELECT cancelado_em,cancelado_por,motivo_cancelamento FROM agendamentos WHERE id=:id'),{'id':ident}).one()
        assert tuple(row)==(None,None,None)
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            conn.execute(text('UPDATE agendamentos SET cancelado_por=:user WHERE id=:id'),{'user':uuid4(),'id':ident})
    assert error.value.orig.pgcode=='23503'
    assert error.value.orig.diag.constraint_name=='agendamentos_cancelado_por_fkey'


def test_fk_auditoria_reverte_cancelamento_e_mantem_intervalo_ocupado(pg,booking):
    from types import SimpleNamespace
    from app.models import Agendamento,Comanda
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    from app.services.persistencia import ConflitoPersistencia
    ident,_=booking
    # Simula usuário autenticado removido antes da gravação da FK de auditoria.
    with Session(pg) as db:
        with pytest.raises(ConflitoPersistencia):
            atualizar_status(ident,AgendamentoStatusUpdate(status='cancelado',motivo_cancelamento='Teste'),db,SimpleNamespace(id=uuid4(),perfil='admin'))
        appointment=db.get(Agendamento,ident)
        command=db.scalar(select(Comanda).where(Comanda.agendamento_id==ident))
        assert appointment.status=='aguardando' and command.status=='aberta'
        assert appointment.cancelado_em is appointment.cancelado_por is appointment.motivo_cancelamento is None
        db.add(Agendamento(cliente_id=appointment.cliente_id,barbeiro_id=appointment.barbeiro_id,data=appointment.data,hora_inicio=appointment.hora_inicio,hora_fim=appointment.hora_fim,status='pendente',origem='recepcao'))
        with pytest.raises(IntegrityError) as error:
            db.commit()
        assert error.value.orig.pgcode=='23P01'
        db.rollback()
        assert db.scalar(text('SELECT 1'))==1
