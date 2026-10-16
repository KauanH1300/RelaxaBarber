"""Duas filiais, transações reais e migração legada sem conexão externa."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from threading import Barrier, Event
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select, text, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_concorrencia import data
from test_modelagem_filiais import populated_legacy, apply
from test_cancelamento_etapa_g import wait_for_lock

EXPAND = 'f04b28c31d57'
CONTRACT = 'a15c39d42e68'


@pytest.fixture
def duas_filiais(pg, data):
    from app.models import Filial, UsuarioFilial, Usuario, PerfilEnum
    with Session(pg) as db:
        first=db.get(Filial,data['filial'])
        second=Filial(nome='Segunda somente teste',empresa_id=first.empresa_id)
        admin=Usuario(nome='Admin',email='admin@example.test',senha_hash='ficticio',perfil=PerfilEnum.ADMIN)
        db.add_all([second,admin]);db.flush()
        db.add(UsuarioFilial(usuario_id=data['user'],filial=second));db.commit()
        return data | {'second':second.id,'admin':admin.id}


def payload(data, filial):
    from app.schemas.agendamento import AgendamentoCreate
    return AgendamentoCreate(cliente_id=data['client'],barbeiro_id=data['user'],filial_id=filial,
        data=date(2099,1,1),hora_inicio=time(9),servicos=[{'servico_id':data['service']}])


def test_reservas_concorrentes_em_filiais_distintas_sao_globais_e_atomicas(pg,duas_filiais):
    from app.models import Usuario,Agendamento,AgendamentoServico,Comanda,ItemComanda
    from app.services.agendamento import criar_agendamento
    from app.services.persistencia import ConflitoPersistencia
    s=duas_filiais;barrier=Barrier(2,timeout=5)
    class Coordinated(Session):
        def flush(self,*a,**kw):
            if any(isinstance(obj,Agendamento) for obj in self.new): barrier.wait()
            return super().flush(*a,**kw)
    def create(filial):
        with Coordinated(pg,autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='10s'"))
            try:
                criar_agendamento(payload(s,filial),db,db.get(Usuario,s['admin']))
                result='ok'
            except ConflitoPersistencia as error:
                assert error.mensagem=='Barbeiro já tem agendamento nesse horário'
                result='conflict'
            assert db.scalar(text('SELECT 1'))==1
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create,[s['filial'],s['second']]))==['conflict','ok']
    with Session(pg) as db:
        for model in (Agendamento,AgendamentoServico,Comanda,ItemComanda): assert db.query(model).count()==1
        assert db.query(Agendamento).one().filial_id==db.query(Comanda).one().filial_id


@pytest.mark.parametrize('target',['vinculo','filial'])
@pytest.mark.parametrize('commit',[True,False])
def test_revogacao_primeiro_criacao_revalida_apos_espera(pg,duas_filiais,target,commit):
    from app.models import Usuario,Agendamento
    from app.services.agendamento import criar_agendamento
    from app.services.errors import SemPermissao
    s=duas_filiais;started=Event();pid=[]
    def create():
        with Session(pg,autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(db.scalar(text('SELECT pg_backend_pid()')));started.set()
            try:
                criar_agendamento(payload(s,s['filial']),db,db.get(Usuario,s['user']))
                return 'ok'
            except SemPermissao:
                assert db.scalar(text('SELECT 1'))==1
                return 'denied'
    with pg.connect() as conn, ThreadPoolExecutor(max_workers=1) as pool:
        transaction=conn.begin()
        if target=='vinculo': conn.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:user AND filial_id=:filial'),s)
        else: conn.execute(text('UPDATE filiais SET ativa=false WHERE id=:filial'),s)
        future=pool.submit(create)
        try:
            assert started.wait(3);wait_for_lock(pg,pid[0])
        finally:
            transaction.commit() if commit else transaction.rollback()
        assert future.result(timeout=10)==('denied' if commit else 'ok')
    with Session(pg) as db: assert db.query(Agendamento).count()==(0 if commit else 1)


@pytest.mark.parametrize('target',['vinculo','filial'])
def test_criacao_primeiro_revogacao_aguarda_commit(pg,duas_filiais,target):
    from app.models import Usuario,Agendamento
    from app.services.agendamento import criar_agendamento
    s=duas_filiais;ready=Event();release=Event();revoking=Event();pid=[]
    class Paused(Session):
        def flush(self,*a,**kw):
            if any(isinstance(obj,Agendamento) for obj in self.new):
                ready.set();assert release.wait(5)
            return super().flush(*a,**kw)
    def create():
        with Paused(pg,autoflush=False) as db:
            return criar_agendamento(payload(s,s['filial']),db,db.get(Usuario,s['user'])).id
    def revoke():
        with pg.begin() as conn:
            conn.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(conn.scalar(text('SELECT pg_backend_pid()')));revoking.set()
            if target=='vinculo': conn.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:user AND filial_id=:filial'),s)
            else: conn.execute(text('UPDATE filiais SET ativa=false WHERE id=:filial'),s)
    with ThreadPoolExecutor(max_workers=2) as pool:
        creation=pool.submit(create)
        try:
            assert ready.wait(3)
            revocation=pool.submit(revoke)
            assert revoking.wait(3);wait_for_lock(pg,pid[0])
        finally: release.set()
        assert creation.result(timeout=10)
        revocation.result(timeout=10)
    with Session(pg) as db: assert db.query(Agendamento).count()==1


def test_constraints_compostas_rejeitam_divergencias_e_nulos(pg,duas_filiais):
    from app.models import Usuario,Agendamento,Comanda
    from app.services.agendamento import criar_agendamento
    s=duas_filiais
    with Session(pg) as db:
        ident=criar_agendamento(payload(s,s['filial']),db,db.get(Usuario,s['admin'])).id
    for column,value in [('filial_id',s['second']),('barbeiro_id',s['other'])]:
        with pytest.raises(IntegrityError) as error:
            with pg.begin() as conn:
                conn.execute(text(f'UPDATE comandas SET {column}=:value WHERE agendamento_id=:id'),{'value':value,'id':ident})
        assert error.value.orig.diag.constraint_name=='fk_comandas_contexto_agendamento'
    for table in ('agendamentos','comandas'):
        with pytest.raises(IntegrityError) as error:
            with pg.begin() as conn: conn.execute(text(f'UPDATE {table} SET filial_id=NULL'))
        assert error.value.orig.pgcode=='23502'
    with pg.connect() as conn:
        clause=conn.scalar(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ex_agendamentos_profissional_periodo'"))
        assert 'filial_id' not in clause and 'barbeiro_id WITH =' in clause
        assert inspect(conn).get_columns('agendamentos')[-1]['name']=='filial_id'


def legacy_snapshot(conn):
    tables=('usuarios','clientes','servicos','agendamentos','agendamento_servicos','comandas','itens_comanda')
    return {table:conn.execute(text(f"SELECT id, md5((to_jsonb(t)-'filial_id')::text) FROM {table} t ORDER BY id")).all() for table in tables}


def test_migracao_povoada_preserva_campos_antigos_e_completa_usuario_do_intervalo(pg_engine,populated_legacy):
    ids=populated_legacy
    with pg_engine.begin() as conn:
        apply(conn,'d82f06a19b35');apply(conn,'e93a17b20c46')
        new=uuid4()
        conn.execute(text("INSERT INTO usuarios(id,nome,email,senha_hash,perfil,ativo) VALUES (:id,'Intervalo','intervalo@example.test','ficticio','BARBEIRO',false)"),{'id':new})
        conn.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id'),{'id':ids['user']})
        before=legacy_snapshot(conn)
        old_constraints=conn.execute(text("SELECT conname,oid FROM pg_constraint WHERE conname IN ('ex_agendamentos_profissional_periodo','ck_agendamentos_intervalo_valido','agendamentos_cancelado_por_fkey') ORDER BY conname")).all()
        clients=conn.execute(text('SELECT id,cliente_id,filial_id FROM cliente_filiais ORDER BY id')).all()
        apply(conn,EXPAND);apply(conn,CONTRACT)
        assert legacy_snapshot(conn)==before
        assert conn.execute(text("SELECT conname,oid FROM pg_constraint WHERE conname IN ('ex_agendamentos_profissional_periodo','ck_agendamentos_intervalo_valido','agendamentos_cancelado_por_fkey') ORDER BY conname")).all()==old_constraints
        assert conn.execute(text('SELECT id,cliente_id,filial_id FROM cliente_filiais ORDER BY id')).all()==clients
        assert conn.scalar(text('SELECT ativo FROM usuario_filiais WHERE usuario_id=:id'),{'id':new}) is False
        assert conn.scalar(text('SELECT ativo FROM usuario_filiais WHERE usuario_id=:id'),{'id':ids['user']}) is False
        assert conn.scalar(text('SELECT count(*) FROM agendamentos a JOIN comandas c ON c.agendamento_id=a.id WHERE a.filial_id=c.filial_id'))==1
        for table in ('agendamentos','comandas'):
            column=next(c for c in inspect(conn).get_columns(table) if c['name']=='filial_id')
            assert not column['nullable'] and column['default'] is None


@pytest.mark.parametrize('invalid',['segunda_filial','comanda_divergente'])
def test_migracao_aborta_sem_reparar_historico(pg_engine,populated_legacy,invalid):
    with pg_engine.begin() as conn:
        apply(conn,'d82f06a19b35');apply(conn,'e93a17b20c46')
        if invalid=='segunda_filial': conn.execute(text("INSERT INTO filiais(id,empresa_id,nome) SELECT :id,id,'Outra teste' FROM empresas"),{'id':uuid4()})
        else: conn.execute(text('UPDATE comandas SET barbeiro_id=:inactive'),populated_legacy)
        before=legacy_snapshot(conn)
    with pytest.raises(RuntimeError):
        with pg_engine.begin() as conn: apply(conn,EXPAND)
    with pg_engine.connect() as conn:
        assert legacy_snapshot(conn)==before
        assert 'filial_id' not in {c['name'] for c in inspect(conn).get_columns('agendamentos')}


def test_restricao_aborta_nulos_sem_reparar(pg_engine,populated_legacy):
    with pg_engine.begin() as conn:
        apply(conn,'d82f06a19b35');apply(conn,'e93a17b20c46');apply(conn,EXPAND)
        conn.execute(text('UPDATE comandas SET filial_id=NULL'))
    with pytest.raises(RuntimeError):
        with pg_engine.begin() as conn: apply(conn,CONTRACT)
    with pg_engine.connect() as conn:
        assert conn.scalar(text('SELECT filial_id FROM comandas')) is None
        assert next(c for c in inspect(conn).get_columns('agendamentos') if c['name']=='filial_id')['nullable']


def test_metadata_contexto_corresponde_ao_banco_e_fk_exige_vinculo(pg,duas_filiais):
    from app.models import Agendamento,Comanda
    s=duas_filiais
    with pg.connect() as conn:
        inspector=inspect(conn)
        for model in (Agendamento,Comanda):
            table=model.__table__
            columns={c['name']:c for c in inspector.get_columns(table.name)}
            assert set(columns)==set(table.c.keys())
            assert not columns['filial_id']['nullable'] and columns['filial_id']['default'] is None
            actual={fk['name']:fk for fk in inspector.get_foreign_keys(table.name)}
            for fk in table.foreign_key_constraints:
                if fk.name:
                    assert fk.name in actual
                    assert actual[fk.name]['constrained_columns']==list(fk.columns.keys())
                    assert actual[fk.name]['referred_columns']==[element.column.name for element in fk.elements]
            assert {i.name for i in table.indexes}<={i['name'] for i in inspector.get_indexes(table.name)}
    # Outro profissional existe na empresa mas não possui vínculo em B.
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            conn.execute(text("""INSERT INTO agendamentos(id,filial_id,cliente_id,barbeiro_id,data,hora_inicio,hora_fim,status,origem)
                VALUES (:id,:second,:client,:other,'2099-01-01','14:00','14:30','pendente','recepcao')"""),s|{'id':uuid4()})
    assert error.value.orig.diag.constraint_name=='fk_agendamentos_profissional_filial'


def test_cancelamento_libera_horario_para_outra_filial(pg,duas_filiais):
    from app.models import Usuario,Comanda,Agendamento
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import criar_agendamento,atualizar_status
    s=duas_filiais
    with Session(pg) as db:
        admin=db.get(Usuario,s['admin'])
        first=criar_agendamento(payload(s,s['filial']),db,admin)
        original=first.id
        atualizar_status(original,AgendamentoStatusUpdate(status='cancelado',motivo_cancelamento='Teste global'),db,admin)
        second=criar_agendamento(payload(s,s['second']),db,admin)
        assert second.filial_id==s['second']
        assert db.get(Agendamento,original).filial_id==s['filial']
        command=db.scalar(select(Comanda).where(Comanda.agendamento_id==original))
        assert command.status=='cancelada' and command.valor_total==30 and len(command.itens)==1


@pytest.mark.parametrize('role',['admin','recepcao','barbeiro_chefe','barbeiro'])
def test_perfis_em_duas_filiais_no_postgresql(pg,duas_filiais,role):
    from app.models import Usuario,UsuarioFilial,Comanda
    from app.api.routes.agendamentos import listar_agenda,buscar_agendamento,atualizar_status
    from app.api.routes.comandas import listar_comandas,buscar_comanda
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import criar_agendamento
    from fastapi import HTTPException
    s=duas_filiais
    with Session(pg,autoflush=False) as db:
        admin=db.get(Usuario,s['admin'])
        first=criar_agendamento(payload(s,s['filial']),db,admin)
        abroad=criar_agendamento(payload(s,s['second']).model_copy(update={'hora_inicio':time(10)}),db,admin)
        if role=='admin': actor=admin
        elif role=='barbeiro': actor=db.get(Usuario,s['other'])
        else:
            actor=Usuario(nome=role,email=f'{role}@example.test',senha_hash='ficticio',perfil=role)
            db.add(UsuarioFilial(usuario=actor,filial_id=s['filial']));db.commit()
        agenda=listar_agenda(date(2099,1,1),db=db,usuario=actor,filial_id=s['filial'])
        commands=listar_comandas(db=db,usuario=actor,filial_id=s['filial'])
        assert len(agenda)==len(commands)==(0 if role=='barbeiro' else 1)
        if role=='admin': assert buscar_agendamento(abroad.id,db,actor).id==abroad.id
        else:
            command=db.scalar(select(Comanda).where(Comanda.agendamento_id==abroad.id))
            for read in (lambda:buscar_agendamento(abroad.id,db,actor),lambda:buscar_comanda(command.id,db,actor)):
                with pytest.raises(HTTPException) as error: read()
                assert error.value.status_code==404
        if role in ('admin','recepcao'):
            assert atualizar_status(first.id,AgendamentoStatusUpdate(status='cancelado'),db,actor).status=='cancelado'
        else:
            with pytest.raises(HTTPException) as error: atualizar_status(first.id,AgendamentoStatusUpdate(status='cancelado'),db,actor)
            assert error.value.status_code==404


def test_cadeia_a_b_preserva_historico_desde_antes_da_modelagem(pg_engine, populated_legacy):
    with pg_engine.begin() as conn:
        before = legacy_snapshot(conn)
        for revision in ('d82f06a19b35', 'e93a17b20c46', EXPAND, CONTRACT):
            apply(conn, revision)
        assert legacy_snapshot(conn) == before
        assert conn.scalar(text('SELECT count(*) FROM cliente_filiais')) == 2
        assert conn.scalar(text('SELECT count(*) FROM usuario_filiais')) == 2
        assert conn.scalar(text('SELECT count(*) FROM agendamentos a JOIN comandas c ON c.agendamento_id=a.id AND c.filial_id=a.filial_id')) == 1


@pytest.mark.parametrize('falhar_primeira', [False, True])
def test_status_concorrentes_entre_filiais_tem_rollback_independente(pg, duas_filiais, falhar_primeira):
    from app.models import Usuario, Agendamento, Comanda
    from app.services.agendamento import criar_agendamento, atualizar_status
    from app.services.persistencia import FalhaPersistencia
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s = duas_filiais
    with Session(pg) as db:
        actor = db.get(Usuario, s['user'])
        first = criar_agendamento(payload(s, s['filial']), db, actor).id
        second = criar_agendamento(payload(s, s['second']).model_copy(update={'hora_inicio': time(10)}), db, actor).id
    barrier = Barrier(2, timeout=5)
    class FalhaCommit(Session):
        def commit(self):
            self.flush()
            raise IntegrityError('falha de teste', {}, Exception('commit recusado'))
    def cancel(ident):
        session_type = FalhaCommit if falhar_primeira and ident == first else Session
        with session_type(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            actor = db.get(Usuario, s['user'])
            barrier.wait()
            try:
                atualizar_status(ident, AgendamentoStatusUpdate(status='cancelado', motivo_cancelamento='Teste concorrente'), db, actor)
                result = 'ok'
            except FalhaPersistencia:
                result = 'rollback'
            assert db.scalar(text('SELECT 1')) == 1
            return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(cancel, [first, second])) == ['rollback' if falhar_primeira else 'ok', 'ok']
    with Session(pg) as db:
        for ident, filial in ((first, s['filial']), (second, s['second'])):
            appointment = db.get(Agendamento, ident)
            command = db.scalar(select(Comanda).where(Comanda.agendamento_id == ident))
            failed = falhar_primeira and ident == first
            assert appointment.filial_id == command.filial_id == filial
            assert appointment.status == ('pendente' if failed else 'cancelado')
            assert command.status == ('pendente' if failed else 'cancelada')
            assert (appointment.cancelado_por == s['user']) is (not failed)
            assert (appointment.cancelado_em is not None) is (not failed)
            assert command.valor_total == 30 and len(command.itens) == 1
