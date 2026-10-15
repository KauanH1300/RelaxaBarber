"""Adiciona perfil interno BARBEIRO_CHEFE, sem converter usuários existentes.

Revision ID: c41a7e0b932d
Revises: 256d632a9c94
"""
from alembic import op

revision = "c41a7e0b932d"
down_revision = "256d632a9c94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLAlchemy persiste o nome do membro Enum, não seu valor em minúsculas.
    # O novo valor só pode ser usado depois do commit da migração PostgreSQL.
    op.execute("ALTER TYPE perfil_enum ADD VALUE IF NOT EXISTS 'BARBEIRO_CHEFE'")


def downgrade() -> None:
    # PostgreSQL não remove valores de enum diretamente. Recriar o tipo exige
    # decisão explícita sobre usuários que já tenham recebido o novo perfil.
    raise NotImplementedError(
        "Remoção de BARBEIRO_CHEFE exige plano manual; nenhum usuário será convertido automaticamente."
    )
