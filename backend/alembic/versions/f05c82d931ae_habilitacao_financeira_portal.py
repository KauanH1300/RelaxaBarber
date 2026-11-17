"""Idempotencia da habilitacao explicita; preserva controles anteriores."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'f05c82d931ae'
down_revision = 'e94f71b820cd'
branch_labels = depends_on = None


def upgrade():
    op.add_column('controles_financeiros_comanda', sa.Column('chave_idempotencia', UUID(as_uuid=True)), schema='public')
    op.add_column('controles_financeiros_comanda', sa.Column('fingerprint', sa.String(64)), schema='public')
    op.create_check_constraint('ck_controle_idempotencia', 'controles_financeiros_comanda',
        '(chave_idempotencia IS NULL AND fingerprint IS NULL) OR '
        '(chave_idempotencia IS NOT NULL AND fingerprint IS NOT NULL AND length(fingerprint)=64)', schema='public')
    # RLS, grants SELECT/INSERT e triggers imutaveis existentes continuam ativos.


def downgrade():
    raise NotImplementedError('Preservar auditoria de habilitacao financeira')
