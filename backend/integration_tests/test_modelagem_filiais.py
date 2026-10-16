"""Migrations reais somente no PostgreSQL descartável validado pela fixture."""
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


LEGACY = ('usuarios', 'clientes', 'servicos', 'agendamentos', 'agendamento_servicos', 'comandas', 'itens_comanda')
STRUCTURE = 'd82f06a19b35'
BOOTSTRAP = 'e93a17b20c46'


def scripts():
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[1] / 'alembic'))
    return ScriptDirectory.from_config(config)


def apply(conn, revision):
    with Operations.context(MigrationContext.configure(conn)):
        scripts().get_revision(revision).module.upgrade()


def reset_to_legacy(engine):
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA public CASCADE'))
        conn.execute(text('CREATE SCHEMA public'))
        for revision in reversed(list(scripts().walk_revisions(base='base', head='a73d92bc6e14'))):
            with Operations.context(MigrationContext.configure(conn)):
                revision.module.upgrade()


def snapshot(conn):
    return {table: conn.execute(text(f'SELECT id, md5(row_to_json(t)::text) FROM public.{table} t ORDER BY id')).all() for table in LEGACY}


@pytest.fixture
def populated_legacy(pg_engine):
    reset_to_legacy(pg_engine)
    ids = dict(user=uuid4(), inactive=uuid4(), client=uuid4(), inactive_client=uuid4(), service=uuid4(), appointment=uuid4(), command=uuid4())
    with pg_engine.begin() as conn:
        conn.execute(text("""INSERT INTO usuarios(id,nome,email,senha_hash,perfil,ativo) VALUES
            (:user,'Ativo','ativo@example.test','ficticio','BARBEIRO',true),
            (:inactive,'Inativo','inativo@example.test','ficticio','RECEPCAO',false)"""), ids)
        conn.execute(text("""INSERT INTO clientes(id,nome,telefone,conta_ativada,saldo,ativo) VALUES
            (:client,'Ativo','0001',false,12.34,true),(:inactive_client,'Inativo','0002',false,0,false)"""), ids)
        conn.execute(text("INSERT INTO servicos(id,nome,preco,tempo_estimado,comissao_padrao,ativo) VALUES (:service,'Corte',30.50,30,10,true)"), ids)
        conn.execute(text("""INSERT INTO agendamentos(id,cliente_id,barbeiro_id,data,hora_inicio,hora_fim,status,origem,cancelado_por,cancelado_em,motivo_cancelamento)
            VALUES (:appointment,:client,:user,'2099-01-01','09:00','09:30','cancelado','recepcao',:user,now(),'Preservar')"""), ids)
        conn.execute(text("INSERT INTO agendamento_servicos(id,agendamento_id,servico_id,preco,tempo_estimado) VALUES (:id,:appointment,:service,30.50,30)"), ids | {'id':uuid4()})
        conn.execute(text("INSERT INTO comandas(id,agendamento_id,cliente_id,barbeiro_id,valor_total,status) VALUES (:command,:appointment,:client,:user,30.50,'cancelada')"), ids)
        conn.execute(text("INSERT INTO itens_comanda(id,comanda_id,tipo,servico_id,descricao,quantidade,preco_unitario) VALUES (:id,:command,'servico',:service,'Corte histórico',1,30.50)"), ids | {'id':uuid4()})
    return ids


def test_backfill_preserva_todos_os_registros_e_inativos(pg_engine, populated_legacy):
    with pg_engine.begin() as conn:
        before = snapshot(conn)
        apply(conn, STRUCTURE)
        apply(conn, BOOTSTRAP)
        assert snapshot(conn) == before
        assert conn.scalar(text('SELECT count(*) FROM empresas')) == 1
        assert conn.scalar(text('SELECT count(*) FROM filiais')) == 1
        assert conn.scalar(text('SELECT count(*) FROM cliente_filiais')) == 2
        assert conn.scalar(text('SELECT count(*) FROM usuario_filiais')) == 2
        assert conn.scalar(text('SELECT ativo FROM usuario_filiais WHERE usuario_id=:id'), {'id': populated_legacy['inactive']}) is False
        assert conn.scalar(text('SELECT ativo FROM usuario_filiais WHERE usuario_id=:id'), {'id': populated_legacy['user']}) is True
        assert conn.scalar(text('SELECT ativo FROM clientes WHERE id=:id'), {'id': populated_legacy['inactive_client']}) is False
        # Nova unidade não copia clientes nem funcionários.
        conn.execute(text("INSERT INTO filiais(id,empresa_id,nome) SELECT :id,id,'Outra somente teste' FROM empresas"), {'id':uuid4()})
        assert conn.scalar(text('SELECT count(*) FROM cliente_filiais')) == 2
        assert conn.scalar(text('SELECT count(*) FROM usuario_filiais')) == 2


def test_bootstrap_vazio_e_metadata_correspondente(pg):
    from app.models import Base
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM empresas')) == 1
        assert conn.scalar(text('SELECT count(*) FROM filiais')) == 1
        assert conn.scalar(text('SELECT count(*) FROM cliente_filiais')) == 0
        assert conn.scalar(text('SELECT count(*) FROM usuario_filiais')) == 0
        inspector = inspect(conn)
        for name in ('empresas', 'filiais', 'usuario_filiais', 'cliente_filiais'):
            actual = {c['name']: c for c in inspector.get_columns(name)}
            expected = Base.metadata.tables[name]
            assert set(actual) == set(expected.c.keys())
            for col in expected.c:
                assert actual[col.name]['nullable'] == col.nullable
            assert {c['name'] for c in inspector.get_unique_constraints(name)} == {c.name for c in expected.constraints if c.__class__.__name__ == 'UniqueConstraint'}
            assert {c['name'] for c in inspector.get_foreign_keys(name)} == {c.name for c in expected.foreign_key_constraints}
            assert {c['name'] for c in inspector.get_check_constraints(name)} == {c.name for c in expected.constraints if c.__class__.__name__ == 'CheckConstraint'}
            assert {c['name'] for c in inspector.get_indexes(name) if not c.get('duplicates_constraint')} == {i.name for i in expected.indexes}


@pytest.mark.parametrize('sql,code', [
    ("INSERT INTO empresas(id,nome) VALUES (:id,'Duplicada')", '23505'),
    ("INSERT INTO empresas(id,nome,singleton) VALUES (:id,'Outra',2)", '23514'),
    ("INSERT INTO filiais(id,empresa_id,nome) VALUES (:id,:id,'Órfã')", '23503'),
    ("INSERT INTO filiais(id,empresa_id,nome,fuso_horario) SELECT :id,id,'Fuso','UTC' FROM empresas", '23514'),
    ("INSERT INTO usuario_filiais(id,usuario_id,filial_id) SELECT :id,:id,id FROM filiais", '23503'),
    ("INSERT INTO cliente_filiais(id,cliente_id,filial_id) SELECT :id,:id,id FROM filiais", '23503'),
])
def test_constraints_rejeitam_dados_invalidos(pg, sql, code):
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            conn.execute(text(sql), {'id':uuid4()})
    assert error.value.orig.pgcode == code


@pytest.mark.parametrize('table,key,source', [('usuario_filiais','usuario_id','user'), ('cliente_filiais','cliente_id','client')])
def test_vinculo_unico_desativacao_logica_e_fk_sem_cascade(pg_engine, populated_legacy, table, key, source):
    with pg_engine.begin() as conn:
        apply(conn, STRUCTURE)
        apply(conn, BOOTSTRAP)
        original = conn.scalar(text(f'SELECT id FROM {table} WHERE {key}=:id'), {'id':populated_legacy[source]})
    with pytest.raises(IntegrityError) as error:
        with pg_engine.begin() as conn:
            conn.execute(text(f'INSERT INTO {table}(id,{key},filial_id) SELECT :id,{key},filial_id FROM {table} WHERE id=:original'), {'id':uuid4(), 'original':original})
    assert error.value.orig.pgcode == '23505'
    with pytest.raises(IntegrityError) as error:
        with pg_engine.begin() as conn:
            conn.execute(text('DELETE FROM filiais'))
    assert error.value.orig.pgcode == '23503'
    if table == 'usuario_filiais':
        with pg_engine.begin() as conn:
            for ativo in (False, True):
                conn.execute(text('UPDATE usuario_filiais SET ativo=:ativo WHERE id=:id'), {'ativo':ativo,'id':original})
                assert conn.scalar(text('SELECT id FROM usuario_filiais WHERE usuario_id=:id'), {'id':populated_legacy[source]}) == original


def test_bootstrap_recusa_estado_inesperado_sem_reparar(pg_engine, populated_legacy):
    with pg_engine.begin() as conn:
        apply(conn, STRUCTURE)
        conn.execute(text("INSERT INTO empresas(id,nome) VALUES (:id,'Não presumir')"), {'id':uuid4()})
        before = snapshot(conn)
    with pytest.raises(RuntimeError, match='tabelas novas vazias'):
        with pg_engine.begin() as conn:
            apply(conn, BOOTSTRAP)
    with pg_engine.connect() as conn:
        assert snapshot(conn) == before
        assert conn.scalar(text('SELECT nome FROM empresas')) == 'Não presumir'
        assert conn.scalar(text('SELECT count(*) FROM filiais')) == 0


def test_falha_no_backfill_reverte_bootstrap_inteiro(pg_engine, populated_legacy):
    with pg_engine.begin() as conn:
        apply(conn, STRUCTURE)
        before = snapshot(conn)
        conn.execute(text("""CREATE FUNCTION recusar_vinculo() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'falha induzida'; END $$"""))
        conn.execute(text('CREATE TRIGGER falha BEFORE INSERT ON cliente_filiais FOR EACH ROW EXECUTE FUNCTION recusar_vinculo()'))
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError):
        with pg_engine.begin() as conn:
            apply(conn, BOOTSTRAP)
    with pg_engine.connect() as conn:
        assert snapshot(conn) == before
        for table in ('empresas', 'filiais', 'usuario_filiais', 'cliente_filiais'):
            assert conn.scalar(text(f'SELECT count(*) FROM {table}')) == 0


def test_downgrade_nao_apaga_vinculos(pg):
    with pg.begin() as conn:
        for revision in (BOOTSTRAP, STRUCTURE):
            with Operations.context(MigrationContext.configure(conn)):
                with pytest.raises(NotImplementedError):
                    scripts().get_revision(revision).module.downgrade()
        assert conn.scalar(text('SELECT count(*) FROM empresas')) == 1
        assert conn.scalar(text('SELECT count(*) FROM filiais')) == 1


def test_backfill_multiplos_lotes_e_novos_cadastros_sem_associacao_implicita(pg_engine):
    reset_to_legacy(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("""INSERT INTO clientes(id,nome,telefone,conta_ativada,saldo,ativo)
            VALUES (:id,'Fictício',:telefone,false,0,true)"""),
            [{'id':uuid4(), 'telefone':str(i)} for i in range(1001)])
        conn.execute(text("""INSERT INTO usuarios(id,nome,email,senha_hash,perfil,ativo)
            VALUES (:id,'Fictício',:email,'ficticio','BARBEIRO',:ativo)"""),
            [{'id':uuid4(), 'email':f'{i}@example.test', 'ativo':i % 2 == 0} for i in range(1001)])
        before = snapshot(conn)
        apply(conn, STRUCTURE)
        apply(conn, BOOTSTRAP)
        assert snapshot(conn) == before
        assert conn.scalar(text('SELECT count(*) FROM cliente_filiais')) == 1001
        assert conn.scalar(text('SELECT count(*) FROM usuario_filiais')) == 1001
        assert conn.scalar(text('SELECT count(*) FROM usuario_filiais WHERE ativo')) == 501
        conn.execute(text("INSERT INTO clientes(id,nome,telefone,conta_ativada,saldo,ativo) VALUES (:id,'Novo','novo',false,0,true)"), {'id':uuid4()})
        assert conn.scalar(text('SELECT count(*) FROM cliente_filiais')) == 1001
        # Não existe trigger de sincronização; novos cadastros serão integrados na B.


def test_grafo_migrations_tem_head_unica():
    assert scripts().get_heads() == ["a15c39d42e68"]
    assert scripts().get_revision("f04b28c31d57").down_revision == BOOTSTRAP
    assert scripts().get_revision(STRUCTURE).down_revision == 'a73d92bc6e14'
    assert scripts().get_revision(BOOTSTRAP).down_revision == STRUCTURE
