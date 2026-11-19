"""Endereço e publicação explícita de filiais na agenda pública."""
from alembic import op
import sqlalchemy as sa

revision = 'a21d4e7b8c90'
down_revision = 'f6c28d19a470'
branch_labels = depends_on = None


def upgrade():
    op.add_column('filiais', sa.Column('endereco', sa.String(300), nullable=True), schema='public')
    op.add_column('filiais', sa.Column('agenda_publica', sa.Boolean(), nullable=False, server_default=sa.false()), schema='public')
    op.create_check_constraint('ck_filial_agenda_endereco', 'filiais', "NOT agenda_publica OR (endereco IS NOT NULL AND length(btrim(endereco)) > 0)", schema='public')
    op.execute('GRANT UPDATE (endereco, agenda_publica) ON public.filiais TO relaxabarber_runtime')


def downgrade():
    raise NotImplementedError('Remover endereços e configurações exige plano explícito de preservação')
