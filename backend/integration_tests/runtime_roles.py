"""Provisionamento EXCLUSIVO do PostgreSQL descartável; não é migração de produção."""
from sqlalchemy import create_engine, text


def provisionar_papeis(engine):
    with engine.begin() as conn:
        for role, attrs in (
            ('rb_horarios_migrador', 'NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'),
            ('relaxabarber_runtime', 'NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'),
            ('relaxabarber_dev_app', 'LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'),
            ('anon', 'NOLOGIN NOSUPERUSER NOBYPASSRLS'),
            ('authenticated', 'NOLOGIN NOSUPERUSER NOBYPASSRLS'),
            ('service_role', 'NOLOGIN NOSUPERUSER BYPASSRLS'),
            ('rb_api_probe', 'LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS'),
        ):
            if not conn.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}):
                conn.execute(text(f'CREATE ROLE {role} {attrs}'))
        conn.execute(text('GRANT relaxabarber_runtime TO relaxabarber_dev_app'))
        conn.execute(text('GRANT anon, authenticated, service_role TO rb_api_probe'))
        # O migrador instala a extensão trusted btree_gist nesta base nova.
        conn.execute(text('GRANT CREATE ON DATABASE relaxabarber_concorrencia_test TO rb_horarios_migrador'))


def conceder_runtime_legado(engine):
    """Reproduz grants auditados nas 11 tabelas, somente na base descartável."""
    tabelas = ('usuarios', 'empresas', 'filiais', 'usuario_filiais', 'clientes', 'cliente_filiais',
               'servicos', 'agendamentos', 'agendamento_servicos', 'comandas', 'itens_comanda')
    updates = {
        'usuarios': 'id', 'empresas': 'id', 'filiais': 'ativa, atualizado_em',
        'usuario_filiais': 'ativo, atualizado_em',
        'clientes': 'nome, telefone, email, ativo, atualizado_em',
        'servicos': 'nome, preco, tempo_estimado, comissao_padrao, ativo, atualizado_em',
        'agendamentos': 'status, cancelado_em, cancelado_por, motivo_cancelamento, atualizado_em',
        'comandas': 'status, data_abertura, data_fechamento, updated_at',
    }
    with engine.begin() as conn:
        conn.execute(text('GRANT USAGE ON SCHEMA public TO relaxabarber_runtime, anon, authenticated, service_role'))
        for tabela in tabelas:
            conn.execute(text(f'REVOKE ALL ON TABLE public.{tabela} FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime'))
            conn.execute(text(f'GRANT SELECT ON TABLE public.{tabela} TO relaxabarber_runtime'))
            if tabela not in ('empresas', 'filiais'):
                conn.execute(text(f'GRANT INSERT ON TABLE public.{tabela} TO relaxabarber_runtime'))
            if tabela in updates:
                conn.execute(text(f'GRANT UPDATE ({updates[tabela]}) ON public.{tabela} TO relaxabarber_runtime'))


def engine_login(pg, usuario='relaxabarber_dev_app'):
    # Conexão efetiva com login diferente, não SET ROLE a partir do superusuário.
    assert pg.url.host == '127.0.0.1' and pg.url.port == 55432
    return create_engine(pg.url.set(username=usuario, password=None), isolation_level='READ COMMITTED',
                         hide_parameters=True, connect_args={'connect_timeout': 3}, pool_size=4, max_overflow=0)
