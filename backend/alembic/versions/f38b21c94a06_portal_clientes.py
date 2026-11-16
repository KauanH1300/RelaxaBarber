"""Contas verificadas, códigos de uso único, limites e sessões do portal."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'f38b21c94a06'
down_revision = 'c54e18f920a7'
branch_labels = depends_on = None
TABELAS = ('portal_clientes_contas', 'portal_clientes_desafios', 'portal_clientes_limites', 'portal_clientes_sessoes')


def proteger(tabela):
    op.execute(f'ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY')
    op.execute(f"""DO $$ DECLARE alvo text; coluna text; BEGIN
        FOREACH alvo IN ARRAY ARRAY['PUBLIC','anon','authenticated','service_role','relaxabarber_runtime'] LOOP
            IF alvo='PUBLIC' OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                EXECUTE format('REVOKE ALL ON public.{tabela} FROM %s', CASE WHEN alvo='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(alvo) END);
                FOR coluna IN SELECT attname FROM pg_attribute WHERE attrelid='public.{tabela}'::regclass AND attnum>0 AND NOT attisdropped LOOP
                    EXECUTE format('REVOKE ALL (%I) ON public.{tabela} FROM %s',coluna,CASE WHEN alvo='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(alvo) END);
                END LOOP;
            END IF;
        END LOOP;
    END $$""")
    acoes = ['SELECT', 'INSERT', 'UPDATE'] + (['DELETE'] if tabela == 'portal_clientes_sessoes' else [])
    op.execute(f"GRANT {', '.join(acoes)} ON public.{tabela} TO relaxabarber_runtime")
    for acao in acoes:
        clausula = 'WITH CHECK (true)' if acao == 'INSERT' else 'USING (true) WITH CHECK (true)' if acao == 'UPDATE' else 'USING (true)'
        op.execute(f'CREATE POLICY portal_runtime_{acao.lower()} ON public.{tabela} FOR {acao} TO relaxabarber_runtime {clausula}')
    op.execute(f"""DO $$ DECLARE alvo text; priv text; BEGIN
        FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                FOREACH priv IN ARRAY ARRAY['SELECT','INSERT','UPDATE','REFERENCES'] LOOP
                    IF has_any_column_privilege(alvo,'public.{tabela}',priv) THEN RAISE EXCEPTION 'Acesso herdado ao portal: %',alvo; END IF;
                END LOOP;
                FOREACH priv IN ARRAY ARRAY['DELETE','TRUNCATE','TRIGGER'] LOOP
                    IF has_table_privilege(alvo,'public.{tabela}',priv) THEN RAISE EXCEPTION 'Acesso herdado ao portal: %',alvo; END IF;
                END LOOP;
                IF current_setting('server_version_num')::integer >= 170000 AND has_table_privilege(alvo,'public.{tabela}','MAINTAIN') THEN
                    RAISE EXCEPTION 'MAINTAIN herdado ao portal: %',alvo;
                END IF;
            END IF;
        END LOOP;
        IF pg_has_role('relaxabarber_runtime',(SELECT relowner FROM pg_class WHERE oid='public.{tabela}'::regclass),'USAGE') THEN
            RAISE EXCEPTION 'Runtime herda proprietario das contas';
        END IF;
    END $$""")


def upgrade():
    op.execute("""DO $$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='relaxabarber_runtime' AND NOT rolsuper AND NOT rolbypassrls) THEN
        RAISE EXCEPTION 'Runtime restrito obrigatorio'; END IF; END $$""")
    op.create_table('portal_clientes_contas',
        sa.Column('cliente_id', UUID(as_uuid=True), sa.ForeignKey('public.clientes.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('email_confirmado', sa.String(255), unique=True, nullable=False),
        sa.Column('verificado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.CheckConstraint('versao > 0', name='ck_portal_conta_versao'), schema='public')
    op.create_table('portal_clientes_desafios',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('finalidade', sa.String(20), nullable=False),
        sa.Column('codigo_hash', sa.String(64), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('cliente_id', UUID(as_uuid=True), sa.ForeignKey('public.clientes.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('dados', sa.JSON(), nullable=True),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tentativas', sa.Integer(), nullable=False),
        sa.Column('consumido', sa.Boolean(), nullable=False),
        sa.CheckConstraint("finalidade IN ('cadastro','recuperacao')", name='ck_portal_desafio_finalidade'),
        sa.CheckConstraint('tentativas BETWEEN 0 AND 5', name='ck_portal_desafio_tentativas'), schema='public')
    op.create_index('ix_portal_desafios_expiracao','portal_clientes_desafios',['expira_em'],schema='public')
    op.create_table('portal_clientes_limites',
        sa.Column('chave', sa.String(64), primary_key=True),
        sa.Column('inicio', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ultimo', sa.DateTime(timezone=True), nullable=False),
        sa.Column('quantidade', sa.Integer(), nullable=False), schema='public')
    op.create_table('portal_clientes_sessoes',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('cliente_id', UUID(as_uuid=True), sa.ForeignKey('public.clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False), schema='public')
    op.create_index('ix_portal_clientes_sessoes_cliente_id','portal_clientes_sessoes',['cliente_id'],schema='public')
    op.create_index('ix_portal_clientes_sessoes_expira_em','portal_clientes_sessoes',['expira_em'],schema='public')
    for tabela in TABELAS:
        proteger(tabela)
    # O runtime só recebe UPDATE por coluna. Esta função sem argumentos apenas
    # serializa o cadastro com a recepção; não amplia acesso a saldo ou outras colunas.
    op.execute("""CREATE FUNCTION public.portal_bloquear_clientes() RETURNS void LANGUAGE plpgsql
        SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
            LOCK TABLE public.clientes IN SHARE ROW EXCLUSIVE MODE;
        END $$""")
    op.execute('REVOKE ALL ON FUNCTION public.portal_bloquear_clientes() FROM PUBLIC')
    op.execute("""DO $$ DECLARE alvo text; BEGIN
        FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                EXECUTE format('REVOKE ALL ON FUNCTION public.portal_bloquear_clientes() FROM %I',alvo);
            END IF;
        END LOOP;
    END $$""")
    op.execute('GRANT EXECUTE ON FUNCTION public.portal_bloquear_clientes() TO relaxabarber_runtime')
    op.execute('GRANT UPDATE (senha_hash, conta_ativada) ON public.clientes TO relaxabarber_runtime')


def downgrade():
    raise NotImplementedError('Downgrade bloqueado: contas e evidencias de verificacao devem ser preservadas')
