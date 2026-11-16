"""Habilitacoes explicitas e idempotencia de reservas do portal, sem backfill."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision='b72f90c31a64'
down_revision='a91c73e52b08'
branch_labels=depends_on=None


def upgrade():
    op.create_table('habilitacoes_servicos',
        sa.Column('filial_id',UUID(as_uuid=True),primary_key=True),
        sa.Column('barbeiro_id',UUID(as_uuid=True),primary_key=True),
        sa.Column('servico_id',UUID(as_uuid=True),sa.ForeignKey('public.servicos.id',ondelete='RESTRICT'),primary_key=True),
        sa.ForeignKeyConstraint(['barbeiro_id','filial_id'],['public.usuario_filiais.usuario_id','public.usuario_filiais.filial_id'],ondelete='RESTRICT'),schema='public')
    op.create_table('portal_clientes_reservas',
        sa.Column('cliente_id',UUID(as_uuid=True),sa.ForeignKey('public.clientes.id',ondelete='RESTRICT'),primary_key=True),
        sa.Column('chave',UUID(as_uuid=True),primary_key=True),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('agendamento_id',UUID(as_uuid=True),sa.ForeignKey('public.agendamentos.id',ondelete='RESTRICT'),nullable=False,unique=True),schema='public')
    for tabela,acoes in [('habilitacoes_servicos',('SELECT','INSERT','DELETE')),('portal_clientes_reservas',('SELECT','INSERT'))]:
        op.execute(f'ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON public.{tabela} FROM PUBLIC, relaxabarber_runtime')
        op.execute(f"""DO $$ DECLARE alvo text; BEGIN
          FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
              EXECUTE format('REVOKE ALL ON public.{tabela} FROM %I',alvo);
              IF has_any_column_privilege(alvo,'public.{tabela}','SELECT,INSERT,UPDATE,REFERENCES') OR has_table_privilege(alvo,'public.{tabela}','DELETE,TRUNCATE,TRIGGER') THEN
                RAISE EXCEPTION 'Acesso indevido a reservas publicas';
              END IF;
            END IF;
          END LOOP;
        END $$""")
        op.execute(f"GRANT {', '.join(acoes)} ON public.{tabela} TO relaxabarber_runtime")
        for acao in acoes:
            clausula='WITH CHECK (true)' if acao=='INSERT' else 'USING (true)'
            op.execute(f'CREATE POLICY reserva_runtime_{acao.lower()} ON public.{tabela} FOR {acao} TO relaxabarber_runtime {clausula}')


def downgrade():
    raise NotImplementedError('Reservas e evidencias devem ser preservadas')
