"""Autoriza o runtime a editar a coluna de observações já existente."""
from alembic import op

revision = 'b64f8d20c371'
down_revision = 'a31d7f05e692'


def upgrade():
    op.execute('GRANT UPDATE (observacoes) ON public.agendamentos TO relaxabarber_runtime')


def downgrade():
    op.execute('REVOKE UPDATE (observacoes) ON public.agendamentos FROM relaxabarber_runtime')
