"""Excecoes negativas por filial; preserva habilitacoes positivas legadas."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'd83e60a719bc'
down_revision = 'b72f90c31a64'
branch_labels = depends_on = None


def upgrade():
    op.create_table('restricoes_servicos',
        sa.Column('filial_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('barbeiro_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('servico_id', UUID(as_uuid=True), sa.ForeignKey('public.servicos.id', ondelete='RESTRICT'), primary_key=True),
        sa.ForeignKeyConstraint(['barbeiro_id', 'filial_id'],
            ['public.usuario_filiais.usuario_id', 'public.usuario_filiais.filial_id'], ondelete='RESTRICT'), schema='public')
    op.execute('ALTER TABLE public.restricoes_servicos ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON public.restricoes_servicos FROM PUBLIC, relaxabarber_runtime')
    op.execute("""DO $$ DECLARE alvo text; BEGIN
      FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
          EXECUTE format('REVOKE ALL ON public.restricoes_servicos FROM %I',alvo);
          IF has_any_column_privilege(alvo,'public.restricoes_servicos','SELECT,INSERT,UPDATE,REFERENCES') OR
             has_table_privilege(alvo,'public.restricoes_servicos','DELETE,TRUNCATE,TRIGGER') THEN
            RAISE EXCEPTION 'Acesso indevido a restricoes de servicos';
          END IF;
        END IF;
      END LOOP;
    END $$""")
    op.execute('GRANT SELECT, INSERT, DELETE ON public.restricoes_servicos TO relaxabarber_runtime')
    for acao in ('SELECT', 'INSERT', 'DELETE'):
        clausula = 'WITH CHECK (true)' if acao == 'INSERT' else 'USING (true)'
        op.execute(f'CREATE POLICY restricao_runtime_{acao.lower()} ON public.restricoes_servicos FOR {acao} TO relaxabarber_runtime {clausula}')


def downgrade():
    raise NotImplementedError('Restricoes devem ser preservadas')
