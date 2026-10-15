"""Auditoria simples do cancelamento, sem alterar registros históricos.

Revision ID: a73d92bc6e14
Revises: f62b18d4a903
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a73d92bc6e14"
down_revision = "f62b18d4a903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nulos em registros antigos: autor, data e motivo não podem ser inferidos.
    op.add_column("agendamentos", sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True), schema="public")
    op.add_column("agendamentos", sa.Column("cancelado_por", postgresql.UUID(as_uuid=True), nullable=True), schema="public")
    op.add_column("agendamentos", sa.Column("motivo_cancelamento", sa.Text(), nullable=True), schema="public")
    op.create_foreign_key("agendamentos_cancelado_por_fkey", "agendamentos", "usuarios", ["cancelado_por"], ["id"], source_schema="public", referent_schema="public")


def downgrade() -> None:
    op.drop_constraint("agendamentos_cancelado_por_fkey", "agendamentos", schema="public", type_="foreignkey")
    op.drop_column("agendamentos", "motivo_cancelamento", schema="public")
    op.drop_column("agendamentos", "cancelado_por", schema="public")
    op.drop_column("agendamentos", "cancelado_em", schema="public")
