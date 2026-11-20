"""Adiciona campos opcionais ao perfil do cliente."""

from alembic import op
import sqlalchemy as sa

revision = 'd927a1c5e340'
down_revision = 'c74f21e6a930'

COLUNAS = ('data_nascimento', 'preferencias')


def upgrade():
    op.add_column('clientes', sa.Column('data_nascimento', sa.Date()), schema='public')
    op.add_column('clientes', sa.Column('preferencias', sa.String(2000)), schema='public')
    op.execute(f'GRANT UPDATE ({", ".join(COLUNAS)}) ON public.clientes TO relaxabarber_runtime')


def downgrade():
    for coluna in reversed(COLUNAS):
        op.drop_column('clientes', coluna, schema='public')
