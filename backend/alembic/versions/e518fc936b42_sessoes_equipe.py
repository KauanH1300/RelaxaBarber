"""Sessões revogáveis e desafios de senha para a equipe."""
import sqlalchemy as sa
from alembic import op

revision = 'e518fc936b42'
down_revision = 'd927a1c5e340'


def upgrade():
    op.create_table('equipe_sessoes',
        sa.Column('jti_hash', sa.String(64), primary_key=True),
        sa.Column('usuario_id', sa.Uuid(), sa.ForeignKey('public.usuarios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revogada_em', sa.DateTime(timezone=True)),
        schema='public')
    op.create_table('equipe_recuperacoes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('usuario_id', sa.Uuid(), sa.ForeignKey('public.usuarios.id', ondelete='CASCADE'), nullable=False),
        sa.Column('codigo_hash', sa.String(64), nullable=False),
        sa.Column('credencial_hash', sa.String(64), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumida_em', sa.DateTime(timezone=True)),
        sa.Column('tentativas', sa.Integer(), nullable=False),
        sa.CheckConstraint('tentativas BETWEEN 0 AND 5', name='ck_equipe_recuperacao_tentativas'),
        schema='public')
    for tabela, campos in [('equipe_sessoes', 'revogada_em'), ('equipe_recuperacoes', 'tentativas, consumida_em')]:
        op.create_index(f'ix_{tabela}_usuario', tabela, ['usuario_id'], schema='public')
        op.create_index(f'ix_{tabela}_expira', tabela, ['expira_em'], schema='public')
        op.execute(f'REVOKE ALL ON public.{tabela} FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
        op.execute(f'GRANT SELECT, INSERT, DELETE ON public.{tabela} TO relaxabarber_runtime')
        op.execute(f'GRANT UPDATE ({campos}) ON public.{tabela} TO relaxabarber_runtime')
    op.execute('GRANT UPDATE (senha_hash, atualizado_em) ON public.usuarios TO relaxabarber_runtime')


def downgrade():
    op.execute('REVOKE UPDATE (senha_hash) ON public.usuarios FROM relaxabarber_runtime')
    op.drop_table('equipe_recuperacoes', schema='public')
    op.drop_table('equipe_sessoes', schema='public')
