"""Autoria cliente sem substituir funcionarios ou alterar registros anteriores."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = 'e94f71b820cd'
down_revision = 'd83e60a719bc'
branch_labels = depends_on = None


def upgrade():
    op.add_column('agendamentos', sa.Column('cancelado_por_cliente', UUID(as_uuid=True), nullable=True), schema='public')
    op.create_foreign_key('fk_agendamento_cliente_cancelamento', 'agendamentos', 'clientes', ['cancelado_por_cliente'], ['id'], source_schema='public', referent_schema='public', ondelete='RESTRICT')
    op.create_check_constraint('ck_agendamento_autor_cancelamento', 'agendamentos', 'cancelado_por IS NULL OR cancelado_por_cliente IS NULL', schema='public')
    op.add_column('reagendamentos', sa.Column('registrado_por_cliente', UUID(as_uuid=True), nullable=True), schema='public')
    op.create_foreign_key('fk_reagendamento_cliente_autor', 'reagendamentos', 'clientes', ['registrado_por_cliente'], ['id'], source_schema='public', referent_schema='public', ondelete='RESTRICT')
    op.alter_column('reagendamentos', 'registrado_por', nullable=True, schema='public')
    op.create_check_constraint('ck_reagendamento_autor', 'reagendamentos', '(registrado_por IS NOT NULL) <> (registrado_por_cliente IS NOT NULL)', schema='public')
    op.execute('GRANT UPDATE (cancelado_por_cliente) ON public.agendamentos TO relaxabarber_runtime')
    # Existing RLS, immutable history trigger and runtime table grants remain in force.
    for tabela in ('reagendamentos',):
        op.execute(f"""DO $$ DECLARE alvo text; BEGIN
          FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=alvo) AND
               has_any_column_privilege(alvo,'public.{tabela}','SELECT,INSERT,UPDATE,REFERENCES') THEN
              RAISE EXCEPTION 'Permissoes indevidas na agenda';
            END IF;
          END LOOP;
        END $$""")


def downgrade():
    raise NotImplementedError('Preservar autoria e historico dos clientes')
