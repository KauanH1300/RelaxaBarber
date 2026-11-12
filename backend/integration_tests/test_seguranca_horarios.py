"""RLS, ACLs e serviços reais com dados fictícios e login PostgreSQL restrito.

Fixtures só aceitam o PostgreSQL local descartável; jamais usar no Supabase.
"""
import asyncio
import json
from urllib.parse import urlencode, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError, DBAPIError
from sqlalchemy.orm import Session

from runtime_roles import engine_login
from test_horarios_filial import semana
from test_modelagem_filiais import scripts


def aplicar(conn, operacao):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    with Operations.context(MigrationContext.configure(conn)):
        getattr(scripts().get_revision('c82f6a1d904b').module, operacao)()


@pytest.fixture
def atores(pg, runtime_pg):
    from app.models import Usuario, PerfilEnum, Filial, UsuarioFilial
    from app.core.security import hash_senha
    with Session(pg) as db:
        filial = db.scalar(select(Filial))
        users = {}
        senha_hash = hash_senha('senha-ficticia-local')
        for perfil in ('admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'):
            user = Usuario(nome=perfil, email=f'{perfil}@example.com', perfil=PerfilEnum(perfil), senha_hash=senha_hash)
            db.add(user)
            db.flush()
            db.add(UsuarioFilial(usuario_id=user.id, filial_id=filial.id))
            users[perfil] = user.id
        outra = Filial(nome='Outra fictícia', empresa_id=filial.empresa_id)
        db.add(outra)
        db.commit()
        return {'filial': filial.id, 'outra': outra.id, 'users': users}


@pytest.fixture
def api_runtime(runtime_pg):
    from app.api.routes import auth, clientes, servico, usuarios, agendamentos, comandas, filiais
    from app.api.exception_handlers import registrar_erros_persistencia
    from app.db.database import get_db
    app = FastAPI()
    registrar_erros_persistencia(app)
    for module in (auth, clientes, servico, usuarios, agendamentos, comandas, filiais):
        app.include_router(module.router)
    def sessao():
        with Session(runtime_pg, autoflush=False) as db:
            yield db
    app.dependency_overrides[get_db] = sessao
    return app


def chamar(app, path, *, method='GET', dados=None, token=None, form=False):
    async def request():
        parsed = urlsplit(path)
        body = urlencode(dados).encode() if form else json.dumps(dados).encode() if dados is not None else b''
        headers = [(b'content-type', b'application/x-www-form-urlencoded' if form else b'application/json')]
        if token:
            headers.append((b'authorization', f'Bearer {token}'.encode()))
        messages, delivered = [], False
        async def receive():
            nonlocal delivered
            if delivered:
                await asyncio.Event().wait()
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        async def send(message):
            messages.append(message)
        await asyncio.wait_for(app({'type': 'http', 'asgi': {'version': '3.0'},
            'http_version': '1.1', 'scheme': 'http', 'method': method, 'path': parsed.path,
            'raw_path': parsed.path.encode(), 'query_string': parsed.query.encode(), 'root_path': '',
            'headers': headers, 'server': ('test', 80), 'client': ('test', 1)}, receive, send), 10)
        code = next(m['status'] for m in messages if m['type'] == 'http.response.start')
        data = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
        return code, json.loads(data) if data else None
    return asyncio.run(request())


def test_papeis_rls_policies_e_privilegios_reais(pg, runtime_pg):
    with pg.connect() as conn:
        info = conn.execute(text("SELECT relrowsecurity, pg_get_userbyid(relowner) FROM pg_class WHERE oid='public.filial_horarios'::regclass")).one()
        assert info == (True, 'rb_horarios_migrador')
        policies = conn.execute(text("SELECT cmd,roles FROM pg_policies WHERE schemaname='public' AND tablename='filial_horarios' ORDER BY cmd")).all()
        assert [(cmd, list(roles)) for cmd, roles in policies] == [
            ('DELETE', ['relaxabarber_runtime']), ('INSERT', ['relaxabarber_runtime']), ('SELECT', ['relaxabarber_runtime'])]
        expressions = conn.execute(text("SELECT cmd,qual,with_check FROM pg_policies WHERE schemaname='public' AND tablename='filial_horarios' ORDER BY cmd")).all()
        assert expressions == [('DELETE', 'true', None), ('INSERT', None, 'true'), ('SELECT', 'true', None)]
        for role in ('anon', 'authenticated', 'service_role', 'relaxabarber_runtime'):
            for privilege in ('SELECT', 'INSERT', 'DELETE', 'UPDATE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN'):
                actual = conn.scalar(text("SELECT has_table_privilege(:role,'public.filial_horarios',:p)"), {'role': role, 'p': privilege})
                assert actual == (role == 'relaxabarber_runtime' and privilege in ('SELECT', 'INSERT', 'DELETE'))
    with runtime_pg.connect() as conn:
        assert conn.scalar(text('SELECT current_user')) == 'relaxabarber_dev_app'
        assert not conn.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user"))


def test_runtime_select_insert_delete_sem_update(pg, runtime_pg):
    from app.models import Filial
    with Session(pg) as db:
        filial = db.scalar(select(Filial.id))
    with runtime_pg.begin() as conn:
        conn.execute(text('INSERT INTO public.filial_horarios(id,filial_id,dia_semana,fechado) VALUES (:id,:f,0,true)'), {'id': uuid4(), 'f': filial})
        assert conn.scalar(text('SELECT count(*) FROM public.filial_horarios')) == 1
        conn.execute(text('DELETE FROM public.filial_horarios'))
        assert conn.scalar(text('SELECT count(*) FROM public.filial_horarios')) == 0


@pytest.mark.parametrize('sql', [
    'UPDATE public.filial_horarios SET fechado=true',
    'TRUNCATE public.filial_horarios',
    'ALTER TABLE public.filial_horarios ADD COLUMN indevida integer',
    'DROP TABLE public.filial_horarios',
    'CREATE TABLE public.indevida(id integer)',
])
def test_runtime_nega_update_truncate_e_ddl(runtime_pg, sql):
    with pytest.raises(ProgrammingError) as erro:
        with runtime_pg.begin() as conn:
            conn.execute(text(sql))
    assert erro.value.orig.pgcode == '42501'


@pytest.mark.parametrize('role', ['anon', 'authenticated', 'service_role'])
@pytest.mark.parametrize('sql', [
    'SELECT * FROM public.filial_horarios',
    "INSERT INTO public.filial_horarios(id,filial_id,dia_semana,fechado) VALUES (gen_random_uuid(),gen_random_uuid(),0,true)",
    'DELETE FROM public.filial_horarios',
    'UPDATE public.filial_horarios SET fechado=true',
    'TRUNCATE public.filial_horarios',
])
def test_api_roles_negados_mesmo_com_bypassrls(pg, role, sql):
    engine = engine_login(pg, 'rb_api_probe')
    try:
        with pytest.raises(ProgrammingError) as erro:
            with engine.begin() as conn:
                conn.execute(text(f'SET LOCAL ROLE {role}'))
                assert conn.scalar(text('SELECT current_user')) == role
                assert conn.scalar(text('SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user')) == (role == 'service_role')
                conn.execute(text(sql))
        assert erro.value.orig.pgcode == '42501'
    finally:
        engine.dispose()


def test_migracao_falha_sem_runtime_e_nao_altera_tabela(pg):
    with pytest.raises(DBAPIError) as erro:
        with pg.begin() as conn:
            conn.execute(text('ALTER ROLE relaxabarber_runtime RENAME TO rb_runtime_ausente'))
            aplicar(conn, 'upgrade')
    assert erro.value.orig.pgcode == 'P0001'
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname='relaxabarber_runtime'")) == 1
        assert conn.scalar(text("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='filial_horarios'")) == 3


def test_criacao_e_seguranca_revertem_juntas_sem_runtime(pg):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    with pg.begin() as conn:
        conn.execute(text('DROP TABLE public.filial_horarios'))
    with pytest.raises(DBAPIError) as erro:
        with pg.begin() as conn:
            conn.execute(text('ALTER ROLE relaxabarber_runtime RENAME TO rb_runtime_ausente'))
            conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
            with Operations.context(MigrationContext.configure(conn)):
                scripts().get_revision('b91e4c7d203a').module.upgrade()
                scripts().get_revision('c82f6a1d904b').module.upgrade()
    assert erro.value.orig.pgcode == 'P0001'
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT to_regclass('public.filial_horarios')")) is None
        assert conn.scalar(text("SELECT count(*) FROM pg_roles WHERE rolname='relaxabarber_runtime'")) == 1


@pytest.mark.parametrize('atributo', ['BYPASSRLS', 'SUPERUSER'])
def test_runtime_privilegiado_aborta_migracao(pg, atributo):
    with pytest.raises(DBAPIError) as erro:
        with pg.begin() as conn:
            conn.execute(text(f'ALTER ROLE relaxabarber_runtime {atributo}'))
            aplicar(conn, 'upgrade')
    assert erro.value.orig.pgcode == 'P0001'


def test_acesso_herdado_api_aborta_sem_mudar_membership(pg):
    with pytest.raises(DBAPIError) as erro:
        with pg.begin() as conn:
            conn.execute(text('GRANT relaxabarber_runtime TO authenticated'))
            aplicar(conn, 'upgrade')
    assert erro.value.orig.pgcode == 'P0001'
    with pg.connect() as conn:
        assert not conn.scalar(text("SELECT pg_has_role('authenticated','relaxabarber_runtime','MEMBER')"))


def test_downgrade_fecha_acesso_preserva_dados_e_upgrade_restaura(pg, runtime_pg):
    from app.models import Filial, Usuario
    from app.services.horarios_filial import atualizar
    with Session(pg) as db:
        filial = db.scalar(select(Filial))
        admin = Usuario(nome='Admin fictício', email='downgrade@example.com', perfil='admin', senha_hash='ficticio')
        db.add(admin)
        db.commit()
        admin_id, filial_id = admin.id, filial.id
    with Session(runtime_pg) as db:
        atualizar(db, db.get(Usuario, admin_id), filial_id, semana())
    with pg.begin() as conn:
        conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        aplicar(conn, 'downgrade')
    with pytest.raises(ProgrammingError):
        with runtime_pg.connect() as conn:
            conn.execute(text('SELECT * FROM public.filial_horarios'))
    with pg.begin() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.filial_horarios')) == 7
        assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.filial_horarios'::regclass"))
        conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        aplicar(conn, 'upgrade')
    with runtime_pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.filial_horarios')) == 7


def test_revoga_grants_por_coluna_sem_mudar_outras_tabelas(pg):
    with pg.begin() as conn:
        antes = conn.execute(text("SELECT relname,relacl::text FROM pg_class WHERE relnamespace='public'::regnamespace AND relname<>'filial_horarios' ORDER BY relname")).all()
        conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        aplicar(conn, 'downgrade')
        conn.execute(text('GRANT SELECT (id), UPDATE (fechado) ON public.filial_horarios TO anon, authenticated, service_role'))
        aplicar(conn, 'upgrade')
        for role in ('anon', 'authenticated', 'service_role'):
            assert not conn.scalar(text("SELECT has_any_column_privilege(:r,'public.filial_horarios','SELECT') OR has_any_column_privilege(:r,'public.filial_horarios','UPDATE')"), {'r': role})
        depois = conn.execute(text("SELECT relname,relacl::text FROM pg_class WHERE relnamespace='public'::regnamespace AND relname<>'filial_horarios' ORDER BY relname")).all()
        assert antes == depois


def test_http_fluxo_completo_login_restrito(api_runtime, atores, runtime_pg):
    app, s = api_runtime, atores
    code, login = chamar(app, '/auth/login', method='POST', form=True,
                         dados={'username': 'admin@example.com', 'password': 'senha-ficticia-local'})
    assert code == 200
    token = login['access_token']
    assert chamar(app, '/auth/me', token=token)[0] == 200
    code, cliente = chamar(app, '/clientes', method='POST', token=token,
                          dados={'nome': 'Cliente fictício', 'telefone': '000001', 'filial_id': str(s['filial'])})
    assert code == 201
    assert chamar(app, f"/clientes/{cliente['id']}?filial_id={s['filial']}", method='PATCH', token=token,
                  dados={'nome': 'Cliente atualizado', 'email': 'cliente@example.com'})[0] == 200
    code, servico = chamar(app, '/servicos/', method='POST', token=token,
                          dados={'nome': 'Corte fictício', 'preco': 30, 'tempo_estimado': 30, 'comissao_padrao': 10})
    assert code == 201
    assert chamar(app, f"/servicos/{servico['id']}", method='PUT', token=token, dados={'nome': 'Corte atualizado'})[0] == 200
    assert chamar(app, '/servicos/')[0] == 200
    path_horarios = f"/filiais/{s['filial']}/horarios"
    assert chamar(app, path_horarios, method='PUT', token=token, dados=semana().model_dump(mode='json'))[0] == 200
    assert chamar(app, path_horarios, token=token)[1]['configurado']
    dados = {'filial_id': str(s['filial']), 'cliente_id': cliente['id'], 'barbeiro_id': str(s['users']['barbeiro']),
             'data': '2099-01-01', 'hora_inicio': '09:00', 'servicos': [{'servico_id': servico['id']}]}
    code, reserva = chamar(app, '/agendamentos', method='POST', token=token, dados=dados)
    assert code == 201
    for status in ('aguardando', 'em_atendimento', 'concluido'):
        assert chamar(app, f"/agendamentos/{reserva['id']}/status?filial_id={s['filial']}",
                      method='PATCH', token=token, dados={'status': status})[0] == 200
    code, painel = chamar(app, f"/comandas/painel?filial_id={s['filial']}", token=token)
    assert code == 200 and painel['total'] == 1
    assert painel['itens'][0]['status'] == 'fechada'
    assert chamar(app, f"/comandas/{painel['itens'][0]['id']}?filial_id={s['filial']}", token=token)[0] == 200
    assert chamar(app, f"/clientes/{cliente['id']}/resumo?filial_id={s['filial']}", token=token)[0] == 200
    # Segunda reserva cancelada preserva itens e auditoria.
    code, segunda = chamar(app, '/agendamentos', method='POST', token=token, dados=dados | {'hora_inicio': '10:00'})
    assert code == 201
    assert chamar(app, f"/agendamentos/{segunda['id']}/status?filial_id={s['filial']}", method='PATCH', token=token,
                  dados={'status': 'cancelado', 'motivo_cancelamento': 'Teste fictício'})[0] == 200
    # Cadastro de usuário/vínculo e desativações lógicas com grants restritos.
    assert chamar(app, '/usuarios', method='POST', token=token, dados={
        'nome': 'Novo fictício', 'email': 'novo@example.com', 'senha': 'senha-ficticia-local',
        'perfil': 'barbeiro', 'filial_ids': [str(s['filial'])]})[0] == 201
    assert chamar(app, f"/filiais/{s['filial']}/usuarios/{s['users']['recepcao']}", method='PUT', token=token,
                  dados={'ativo': False})[0] == 200
    assert chamar(app, f"/filiais/{s['outra']}", method='DELETE', token=token)[0] == 204
    assert chamar(app, f"/servicos/{servico['id']}", method='DELETE', token=token)[0] == 204
    assert chamar(app, f"/clientes/{cliente['id']}", method='DELETE', token=token)[0] == 204


@pytest.mark.parametrize('perfil', ['recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_http_expediente_somente_admin_e_filial_autorizada(api_runtime, atores, perfil):
    from app.core.security import criar_token
    token = criar_token(atores['users'][perfil])
    path = f"/filiais/{atores['filial']}/horarios"
    assert chamar(api_runtime, path, token=token)[0] == 200
    assert chamar(api_runtime, path, method='PUT', token=token, dados=semana().model_dump(mode='json'))[0] == 403
    assert chamar(api_runtime, f"/filiais/{atores['outra']}/horarios", token=token)[0] == 403
