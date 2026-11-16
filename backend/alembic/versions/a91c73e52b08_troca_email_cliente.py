"""Troca de e-mail confirmada nos dois contatos e consistencia de identidade."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'a91c73e52b08'
down_revision = 'f38b21c94a06'
branch_labels = depends_on = None


def upgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM public.clientes c JOIN public.portal_clientes_contas p ON p.cliente_id=c.id
            WHERE lower(trim(c.email)) IS DISTINCT FROM p.email_confirmado) THEN
            RAISE EXCEPTION 'Identidade inconsistente preexistente; migracao interrompida';
        END IF;
    END $$""")
    op.create_table('portal_clientes_trocas_email',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('cliente_id', UUID(as_uuid=True), sa.ForeignKey('public.clientes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('email_atual', sa.String(255), nullable=False),
        sa.Column('email_novo', sa.String(255), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('etapa', sa.String(10), nullable=False),
        sa.Column('codigo_hash', sa.String(64), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('tentativas', sa.Integer(), nullable=False),
        sa.Column('consumido', sa.Boolean(), nullable=False),
        sa.CheckConstraint("etapa IN ('atual','novo')", name='ck_troca_email_etapa'),
        sa.CheckConstraint('tentativas BETWEEN 0 AND 5', name='ck_troca_email_tentativas'), schema='public')
    op.create_index('ix_portal_clientes_trocas_email_cliente_id', 'portal_clientes_trocas_email', ['cliente_id'], schema='public')
    table = 'public.portal_clientes_trocas_email'
    op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
    op.execute(f'REVOKE ALL ON {table} FROM PUBLIC')
    op.execute(f'REVOKE ALL ON {table} FROM relaxabarber_runtime')
    op.execute(f"""DO $$ DECLARE alvo text; BEGIN
        FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                EXECUTE format('REVOKE ALL ON {table} FROM %I',alvo);
                IF has_any_column_privilege(alvo,'{table}','SELECT') OR has_table_privilege(alvo,'{table}','INSERT,UPDATE,DELETE,TRUNCATE') THEN
                    RAISE EXCEPTION 'Acesso indevido a trocas de email';
                END IF;
            END IF;
        END LOOP;
    END $$""")
    op.execute(f'GRANT SELECT, INSERT, UPDATE ON {table} TO relaxabarber_runtime')
    for action in ('SELECT','INSERT','UPDATE'):
        clause = 'WITH CHECK (true)' if action == 'INSERT' else 'USING (true) WITH CHECK (true)' if action == 'UPDATE' else 'USING (true)'
        op.execute(f'CREATE POLICY troca_runtime_{action.lower()} ON {table} FOR {action} TO relaxabarber_runtime {clause}')
    op.execute('GRANT UPDATE (email) ON public.clientes TO relaxabarber_runtime')
    # Deferred checks see the final state of both updates, regardless of flush order.
    # Administrative edits cannot leave a verified identity pointing at another email.
    op.execute("""CREATE FUNCTION public.portal_validar_email_consistente() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
        DECLARE alvo uuid; BEGIN
            IF TG_TABLE_NAME='clientes' THEN alvo=NEW.id; ELSE alvo=NEW.cliente_id; END IF;
            IF EXISTS(SELECT 1 FROM public.clientes c JOIN public.portal_clientes_contas p ON p.cliente_id=c.id
                WHERE c.id=alvo AND lower(trim(c.email)) IS DISTINCT FROM p.email_confirmado) THEN
                RAISE EXCEPTION 'Troca de email exige verificacao no portal' USING ERRCODE='23514';
            END IF;
            RETURN NULL;
        END $$""")
    op.execute('REVOKE ALL ON FUNCTION public.portal_validar_email_consistente() FROM PUBLIC')
    op.execute('CREATE CONSTRAINT TRIGGER portal_email_cliente AFTER UPDATE OF email ON public.clientes DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.portal_validar_email_consistente()')
    op.execute('CREATE CONSTRAINT TRIGGER portal_email_conta AFTER INSERT OR UPDATE OF email_confirmado ON public.portal_clientes_contas DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.portal_validar_email_consistente()')


def downgrade():
    raise NotImplementedError('Historico de verificacao deve ser preservado')
