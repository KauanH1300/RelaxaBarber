"""Verificação de login ADMIN e dispositivos confiáveis."""
import sqlalchemy as sa
from alembic import op

revision = '5ce84d69be21'
down_revision = '3bf126fd81a0'

TABELA = 'equipe_dispositivos_confiaveis'


def upgrade():
    op.add_column('equipe_sessoes', sa.Column('admin_verificado', sa.Boolean(), nullable=False,
                                            server_default=sa.false()), schema='public')
    op.add_column('equipe_recuperacoes', sa.Column('login_token_hash', sa.String(64)), schema='public')
    op.add_column('equipe_recuperacoes', sa.Column('login_ate', sa.DateTime(timezone=True)), schema='public')
    op.add_column('equipe_recuperacoes', sa.Column('login_enviado_em', sa.DateTime(timezone=True)), schema='public')
    op.create_unique_constraint('uq_equipe_recuperacoes_login_token_hash', 'equipe_recuperacoes',
                                ['login_token_hash'], schema='public')
    op.execute('GRANT UPDATE (codigo_hash, expira_em, login_enviado_em) '
               'ON public.equipe_recuperacoes TO relaxabarber_runtime')
    op.create_table(
        TABELA,
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('usuario_id', sa.Uuid(), sa.ForeignKey('public.usuarios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('credencial_hash', sa.String(64), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        schema='public',
    )
    op.create_index('ix_equipe_dispositivos_usuario', TABELA, ['usuario_id', 'expira_em'], schema='public')
    op.execute(f'ALTER TABLE public.{TABELA} ENABLE ROW LEVEL SECURITY')
    op.execute(f'REVOKE ALL ON public.{TABELA} FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
    op.execute(f'CREATE POLICY equipe_dispositivos_runtime ON public.{TABELA} '
               'FOR ALL TO relaxabarber_runtime USING (true) WITH CHECK (true)')
    op.execute(f'GRANT SELECT, INSERT, DELETE ON public.{TABELA} TO relaxabarber_runtime')


def downgrade():
    op.drop_column('equipe_sessoes', 'admin_verificado', schema='public')
    op.drop_table(TABELA, schema='public')
    op.execute('REVOKE UPDATE (codigo_hash, expira_em, login_enviado_em) '
               'ON public.equipe_recuperacoes FROM relaxabarber_runtime')
    op.execute("DELETE FROM public.equipe_recuperacoes WHERE finalidade = 'login_admin'")
    op.drop_constraint('uq_equipe_recuperacoes_login_token_hash', 'equipe_recuperacoes',
                       schema='public', type_='unique')
    for coluna in ('login_enviado_em', 'login_ate', 'login_token_hash'):
        op.drop_column('equipe_recuperacoes', coluna, schema='public')
