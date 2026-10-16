"""Guarda de reservas sob filial UPDATE contra agendas com filial SHARE."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_contexto_filiais import duas_filiais, payload
from test_concorrencia import data
from test_cancelamento_etapa_g import wait_for_lock


def manage(db, s, target):
    from app.models import Usuario
    from app.services.gestao_filiais import definir_vinculo, desativar_filial
    actor = db.get(Usuario, s['admin'])
    if target == 'filial':
        return desativar_filial(db, actor, s['filial'])
    return definir_vinculo(db, actor, s['filial'], s['user'], False)


@pytest.mark.parametrize('target', ['filial', 'vinculo'])
@pytest.mark.parametrize('confirmar', [True, False])
def test_gestao_primeiro_criacao_revalida_apos_commit_ou_rollback(pg, duas_filiais, target, confirmar):
    from app.models import Usuario, Agendamento
    from app.services.agendamento import criar_agendamento
    from app.services.errors import SemPermissao
    from app.services.persistencia import FalhaPersistencia
    s = duas_filiais
    ready, release, started = Event(), Event(), Event()
    pid = []
    class Paused(Session):
        def commit(self):
            self.flush()
            ready.set()
            assert release.wait(5)
            if not confirmar:
                raise IntegrityError('teste', {}, Exception('rollback induzido'))
            return super().commit()
    def management():
        with Paused(pg, autoflush=False) as db:
            try: manage(db, s, target)
            except FalhaPersistencia:
                assert not confirmar
    def create():
        with Session(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            started.set()
            try:
                criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['user']))
                return 'ok'
            except SemPermissao:
                assert db.scalar(text('SELECT 1')) == 1
                return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(management)
        try:
            assert ready.wait(3)
            second = pool.submit(create)
            assert started.wait(3)
            wait_for_lock(pg, pid[0])
        finally: release.set()
        first.result(timeout=10)
        assert second.result(timeout=10) == ('denied' if confirmar else 'ok')
    with Session(pg) as db: assert db.query(Agendamento).count() == (0 if confirmar else 1)


@pytest.mark.parametrize('target', ['filial', 'vinculo'])
@pytest.mark.parametrize('confirmar', [True, False])
def test_criacao_primeiro_gestao_rele_reserva_e_recusa_409(pg, duas_filiais, target, confirmar):
    from app.models import Usuario, Filial, UsuarioFilial, Agendamento
    from app.services.agendamento import criar_agendamento
    from app.services.errors import ConflitoGestaoFilial
    from app.services.persistencia import FalhaPersistencia
    s = duas_filiais
    ready, release, started = Event(), Event(), Event()
    pid = []
    class Paused(Session):
        def commit(self):
            self.flush()
            ready.set()
            assert release.wait(5)
            if not confirmar: raise IntegrityError('teste', {}, Exception('rollback induzido'))
            return super().commit()
    def create():
        with Paused(pg, autoflush=False) as db:
            try: criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['user']))
            except FalhaPersistencia: assert not confirmar
    def management():
        with Session(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(db.scalar(text('SELECT pg_backend_pid()')));started.set()
            try:
                manage(db, s, target)
                return 'ok'
            except ConflitoGestaoFilial:
                assert db.scalar(text('SELECT 1')) == 1
                return '409'
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create)
        try:
            assert ready.wait(3)
            second = pool.submit(management)
            assert started.wait(3);wait_for_lock(pg, pid[0])
        finally: release.set()
        first.result(timeout=10)
        assert second.result(timeout=10) == ('409' if confirmar else 'ok')
    with Session(pg) as db:
        assert db.query(Agendamento).count() == (1 if confirmar else 0)
        assert db.get(Filial, s['filial']).ativa is (confirmar if target == 'filial' else True)
        link = db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == s['user'], UsuarioFilial.filial_id == s['filial']))
        assert link.ativo is (confirmar if target == 'vinculo' else True)


@pytest.mark.parametrize('target', ['filial', 'vinculo'])
@pytest.mark.parametrize('status', ['cancelado', 'em_atendimento'])
def test_status_primeiro_gestao_observa_estado_confirmado(pg, duas_filiais, target, status):
    from app.models import Usuario, Agendamento, Comanda
    from app.services.agendamento import criar_agendamento, atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.errors import ConflitoGestaoFilial
    s = duas_filiais
    with Session(pg) as db: ident = criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['user'])).id
    ready, release, started = Event(), Event(), Event()
    pid = []
    class Paused(Session):
        def commit(self):
            self.flush();ready.set();assert release.wait(5)
            return super().commit()
    def update():
        with Paused(pg) as db: atualizar_status(ident, AgendamentoStatusUpdate(status=status), db, db.get(Usuario, s['user']))
    def management():
        with Session(pg) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(db.scalar(text('SELECT pg_backend_pid()')));started.set()
            try:
                manage(db, s, target)
                return 'ok'
            except ConflitoGestaoFilial: return '409'
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(update)
        try:
            assert ready.wait(3)
            second = pool.submit(management)
            assert started.wait(3);wait_for_lock(pg, pid[0])
        finally: release.set()
        first.result(timeout=10)
        assert second.result(timeout=10) == ('ok' if status == 'cancelado' else '409')
    with Session(pg) as db:
        assert db.get(Agendamento, ident).status == status
        assert db.scalar(select(Comanda).where(Comanda.agendamento_id == ident)).status == ('cancelada' if status == 'cancelado' else 'aberta')


@pytest.mark.parametrize('target', ['filial', 'vinculo'])
def test_rollback_gestao_preserva_atividade_e_historico(pg, duas_filiais, target):
    from app.models import Filial, UsuarioFilial
    from app.services.persistencia import FalhaPersistencia
    s = duas_filiais
    class Failed(Session):
        def commit(self):
            self.flush()
            raise IntegrityError('teste', {}, Exception('falha induzida'))
    with Failed(pg) as db:
        with pytest.raises(FalhaPersistencia): manage(db, s, target)
        assert db.scalar(text('SELECT 1')) == 1
    with Session(pg) as db:
        assert db.get(Filial, s['filial']).ativa
        assert db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == s['user'], UsuarioFilial.filial_id == s['filial'])).ativo


def test_criacao_concorrente_vinculo_admin_e_idempotente(pg, duas_filiais):
    from threading import Barrier
    from app.models import Usuario, UsuarioFilial
    from app.services.gestao_filiais import definir_vinculo
    s = duas_filiais
    barrier = Barrier(2, timeout=5)
    def create():
        with Session(pg) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            actor = db.get(Usuario, s['admin'])
            barrier.wait()
            return definir_vinculo(db, actor, s['second'], s['other'], True).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: create(), range(2)))
    assert ids[0] == ids[1]
    with Session(pg) as db:
        assert db.query(UsuarioFilial).filter(UsuarioFilial.usuario_id == s['other'], UsuarioFilial.filial_id == s['second']).count() == 1
