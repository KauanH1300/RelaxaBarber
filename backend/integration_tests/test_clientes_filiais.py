"""Vínculos transacionais com concorrência PostgreSQL, sem dados externos."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from datetime import time
from uuid import uuid4

import pytest
from sqlalchemy import select, text, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_contexto_filiais import duas_filiais, payload
from test_concorrencia import data
from test_cancelamento_etapa_g import wait_for_lock


@pytest.mark.parametrize('mesma_filial', [True, False])
def test_primeiros_agendamentos_concorrentes_sem_duplicar_vinculos(pg, duas_filiais, mesma_filial):
    from app.models import Usuario, Cliente, ClienteFilial, Agendamento, Comanda, ItemComanda
    from app.services.agendamento import criar_agendamento
    s = duas_filiais
    barrier = Barrier(2, timeout=5)
    class Coordinated(Session):
        def execute(self, statement, *args, **kwargs):
            if getattr(statement, 'is_insert', False) and statement.table.name == 'cliente_filiais':
                barrier.wait()
            return super().execute(statement, *args, **kwargs)
    def create(second):
        with Coordinated(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            dados = payload(s, s['filial'] if mesma_filial or not second else s['second'])
            if second:
                dados = dados.model_copy(update={'barbeiro_id': s['other']}) if mesma_filial else dados.model_copy(update={'hora_inicio': time(10)})
            return criar_agendamento(dados, db, db.get(Usuario, s['admin'])).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(create, [False, True]))) == 2
    with Session(pg) as db:
        assert db.query(Cliente).count() == 1
        links = db.scalars(select(ClienteFilial)).all()
        assert len(links) == (1 if mesma_filial else 2)
        assert {v.cliente_id for v in links} == {s['client']}
        for model in (Agendamento, Comanda, ItemComanda):
            assert db.query(model).count() == 2


@pytest.mark.parametrize('confirmar_primeira', [True, False])
def test_disputa_vinculo_aguarda_commit_ou_rollback_da_primeira(pg, duas_filiais, confirmar_primeira):
    from app.models import Usuario, ClienteFilial, Agendamento, Comanda
    from app.services.agendamento import criar_agendamento
    from app.services.persistencia import FalhaPersistencia
    s = duas_filiais
    ready, release, attempting = Event(), Event(), Event()
    pid = []
    class Paused(Session):
        def commit(self):
            self.flush()
            ready.set()
            assert release.wait(5)
            if not confirmar_primeira:
                raise IntegrityError('teste', {}, Exception('commit recusado'))
            return super().commit()
    class Competitor(Session):
        def execute(self, statement, *a, **kw):
            if getattr(statement, 'is_insert', False) and statement.table.name == 'cliente_filiais':
                attempting.set()
            return super().execute(statement, *a, **kw)
    def create_first():
        with Paused(pg, autoflush=False) as db:
            try:
                criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['admin']))
                return 'ok'
            except FalhaPersistencia:
                assert db.scalar(text('SELECT 1')) == 1
                return 'rollback'
    def create_second():
        with Competitor(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            dados = payload(s, s['filial']).model_copy(update={'barbeiro_id': s['other']})
            return criar_agendamento(dados, db, db.get(Usuario, s['admin'])).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create_first)
        try:
            assert ready.wait(3)
            second = pool.submit(create_second)
            assert attempting.wait(3)
            wait_for_lock(pg, pid[0])
        finally:
            release.set()
        assert first.result(timeout=10) == ('ok' if confirmar_primeira else 'rollback')
        assert second.result(timeout=10)
    with Session(pg) as db:
        assert db.query(ClienteFilial).count() == 1
        assert db.query(Agendamento).count() == db.query(Comanda).count() == (2 if confirmar_primeira else 1)


@pytest.mark.parametrize('existente', [True, False])
@pytest.mark.parametrize('phase', ['vinculo', 'comanda', 'commit'])
def test_falha_reverte_somente_novo_vinculo_e_atendimento(pg, duas_filiais, existente, phase):
    from app.models import Usuario, ClienteFilial, Agendamento, AgendamentoServico, Comanda, ItemComanda
    from app.services.agendamento import criar_agendamento
    from app.services.persistencia import FalhaPersistencia
    s = duas_filiais
    with Session(pg) as db:
        if existente:
            db.add(ClienteFilial(cliente_id=s['client'], filial_id=s['filial']))
            db.commit()
        previous = [(v.id, v.data_cadastro) for v in db.scalars(select(ClienteFilial))]
    def fail_sql(conn, cursor, statement, params, context, many):
        table = 'cliente_filiais' if phase == 'vinculo' else 'comandas'
        if statement.startswith(f'INSERT INTO {table} '):
            raise IntegrityError('teste', {}, Exception('falha induzida'))
    def fail_commit(session):
        session.flush()
        raise IntegrityError('teste', {}, Exception('falha induzida'))
    with Session(pg, autoflush=False) as db:
        target, name, callback = (db, 'before_commit', fail_commit) if phase == 'commit' else (pg, 'before_cursor_execute', fail_sql)
        event.listen(target, name, callback)
        try:
            with pytest.raises(FalhaPersistencia):
                criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['admin']))
        finally:
            event.remove(target, name, callback)
        assert [(v.id, v.data_cadastro) for v in db.scalars(select(ClienteFilial))] == previous
        for model in (Agendamento, AgendamentoServico, Comanda, ItemComanda):
            assert db.query(model).count() == 0


def test_cadastro_concorrente_mesmo_telefone_nao_duplica_cliente_ou_vinculos(pg, duas_filiais):
    from app.models import Usuario, Cliente, ClienteFilial
    from app.api.routes.clientes import criar_cliente
    from app.schemas.cliente import ClienteCreate
    from app.services.persistencia import ConflitoPersistencia
    s = duas_filiais
    barrier = Barrier(2, timeout=5)
    class Coordinated(Session):
        def flush(self, *a, **kw):
            if any(isinstance(obj, Cliente) for obj in self.new):
                barrier.wait()
            return super().flush(*a, **kw)
    def create(filial_id):
        with Coordinated(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            try:
                criar_cliente(ClienteCreate(nome='Único', telefone='compartilhado', filial_id=filial_id), db, db.get(Usuario, s['admin']))
                return 'ok'
            except ConflitoPersistencia:
                assert db.scalar(text('SELECT 1')) == 1
                return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, [s['filial'], s['second']])) == ['conflict', 'ok']
    with Session(pg) as db:
        cliente = db.scalar(select(Cliente).where(Cliente.telefone == 'compartilhado'))
        assert db.query(Cliente).count() == 2
        assert db.query(ClienteFilial).filter(ClienteFilial.cliente_id == cliente.id).count() == 1


def test_cancelamento_preserva_vinculo_id_data_e_catalogos_globais(pg, duas_filiais):
    from app.models import Usuario, ClienteFilial, Cliente, Comanda
    from app.services.agendamento import criar_agendamento, atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s = duas_filiais
    with Session(pg) as db:
        user = db.get(Usuario, s['admin'])
        first = criar_agendamento(payload(s, s['filial']), db, user)
        link = db.scalar(select(ClienteFilial))
        before = (link.id, link.data_cadastro)
        atualizar_status(first.id, AgendamentoStatusUpdate(status='cancelado'), db, user)
        criar_agendamento(payload(s, s['filial']), db, user)
        second = criar_agendamento(payload(s, s['second']).model_copy(update={'hora_inicio': time(10)}), db, user)
        db.expire_all()
        assert db.query(Cliente).count() == 1
        links = db.scalars(select(ClienteFilial).where(ClienteFilial.filial_id == s['filial'])).all()
        assert len(links) == 1 and (links[0].id, links[0].data_cadastro) == before
        assert db.query(ClienteFilial).count() == 2
        assert db.scalar(select(Comanda).where(Comanda.agendamento_id == second.id)).filial_id == s['second']


@pytest.mark.parametrize('phase', ['vinculo', 'commit'])
def test_cadastro_cliente_e_vinculo_revertem_juntos(pg, duas_filiais, phase):
    from app.models import Usuario, Cliente, ClienteFilial
    from app.api.routes.clientes import criar_cliente
    from app.schemas.cliente import ClienteCreate
    from app.services.persistencia import FalhaPersistencia
    s = duas_filiais
    def fail_sql(conn, cursor, statement, params, context, many):
        if statement.startswith('INSERT INTO cliente_filiais '):
            raise IntegrityError('teste', {}, Exception('falha induzida'))
    def fail_commit(session):
        session.flush()
        raise IntegrityError('teste', {}, Exception('falha induzida'))
    with Session(pg, autoflush=False) as db:
        target, name, callback = (db, 'before_commit', fail_commit) if phase == 'commit' else (pg, 'before_cursor_execute', fail_sql)
        event.listen(target, name, callback)
        try:
            with pytest.raises(FalhaPersistencia):
                criar_cliente(ClienteCreate(nome='Rollback', telefone='rollback', filial_id=s['filial']), db, db.get(Usuario, s['admin']))
        finally:
            event.remove(target, name, callback)
        assert db.query(Cliente).count() == 1
        assert db.query(ClienteFilial).count() == 0


@pytest.mark.parametrize('invalid', ['cliente', 'filial'])
def test_upsert_nao_ignora_fk_invalida_e_sessao_recupera(pg, duas_filiais, invalid):
    from app.services.clientes import garantir_vinculo
    from app.services.persistencia import transacao_escrita, ConflitoPersistencia
    from app.models import ClienteFilial
    s = duas_filiais
    with Session(pg) as db:
        with pytest.raises(ConflitoPersistencia):
            with transacao_escrita(db):
                garantir_vinculo(db, uuid4() if invalid == 'cliente' else s['client'], uuid4() if invalid == 'filial' else s['filial'])
        assert db.scalar(text('SELECT 1')) == 1
        assert db.query(ClienteFilial).count() == 0


def test_pesquisa_global_e_detalhe_local_no_postgresql(pg, duas_filiais):
    from app.models import Usuario, UsuarioFilial, Cliente
    from app.api.routes.clientes import criar_cliente, pesquisar_clientes, listar_clientes, buscar_cliente, editar_cliente
    from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClientePesquisaOut, ClienteOut
    from app.services.agendamento import criar_agendamento
    from fastapi import HTTPException
    s = duas_filiais
    with Session(pg) as db:
        admin = db.get(Usuario, s['admin'])
        reception = Usuario(nome='Recepção', email='recepcao@example.com', senha_hash='ficticio', perfil='recepcao')
        db.add(UsuarioFilial(usuario=reception, filial_id=s['filial']))
        db.commit()
        foreign = criar_cliente(ClienteCreate(nome='De outra filial', telefone='outra', filial_id=s['second']), db, admin)
        foreign_id = foreign.id
        criar_agendamento(payload(s, s['filial']), db, admin)
        found = pesquisar_clientes(db=db, usuario=reception)
        assert {c.id for c in found} == {s['client'], foreign_id}
        assert all(set(ClientePesquisaOut.model_validate(c).model_dump()) == {'id', 'nome', 'telefone'} for c in found)
        local = listar_clientes(db=db, usuario=reception)
        assert [c.id for c in local] == [s['client']]
        assert 'saldo' not in ClienteOut.model_validate(local[0]).model_dump()
        for action in (
            lambda: buscar_cliente(foreign_id, db, reception),
            lambda: editar_cliente(foreign_id, ClienteUpdate(nome='Negado'), db, reception),
        ):
            with pytest.raises(HTTPException) as error:
                action()
            assert error.value.status_code == 404
        assert db.get(Cliente, foreign_id).nome == 'De outra filial'
        with pytest.raises(HTTPException) as error:
            listar_clientes(db=db, usuario=reception, filial_id=s['second'])
        assert error.value.status_code == 403


@pytest.mark.parametrize('confirmar_desativacao', [True, False])
def test_cliente_revalidado_apos_desativacao_concorrente(pg, duas_filiais, confirmar_desativacao):
    from app.models import Usuario, ClienteFilial, Agendamento
    from app.services.agendamento import criar_agendamento
    from app.services.errors import ClienteInativo
    s = duas_filiais
    ready = Event()
    pid = []
    def create():
        with Session(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            ready.set()
            try:
                criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['admin']))
                return 'ok'
            except ClienteInativo:
                assert db.scalar(text('SELECT 1')) == 1
                return 'inativo'
    with pg.connect() as conn, ThreadPoolExecutor(max_workers=1) as pool:
        transaction = conn.begin()
        conn.execute(text('UPDATE clientes SET ativo=false WHERE id=:client'), s)
        future = pool.submit(create)
        try:
            assert ready.wait(3)
            wait_for_lock(pg, pid[0])
        finally:
            transaction.commit() if confirmar_desativacao else transaction.rollback()
        assert future.result(timeout=10) == ('inativo' if confirmar_desativacao else 'ok')
    with Session(pg) as db:
        assert db.query(ClienteFilial).count() == db.query(Agendamento).count() == (0 if confirmar_desativacao else 1)
