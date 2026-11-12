"""Expediente semanal opcional, sem backfill nem alteração de reservas.

Revision ID: b91e4c7d203a
Revises: a15c39d42e68
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b91e4c7d203a'
down_revision = 'a15c39d42e68'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'filial_horarios',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filial_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dia_semana', sa.Integer(), nullable=False),
        sa.Column('fechado', sa.Boolean(), nullable=False),
        sa.Column('hora_inicio', sa.Time(timezone=False), nullable=True),
        sa.Column('hora_fim', sa.Time(timezone=False), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['filial_id'], ['public.filiais.id'], name='fk_filial_horarios_filial'),
        sa.UniqueConstraint('filial_id', 'dia_semana', name='uq_filial_horarios_dia'),
        sa.CheckConstraint('dia_semana BETWEEN 0 AND 6', name='ck_filial_horarios_dia'),
        sa.CheckConstraint(
            '(fechado AND hora_inicio IS NULL AND hora_fim IS NULL) OR '
            '(NOT fechado AND hora_inicio IS NOT NULL AND hora_fim IS NOT NULL AND hora_inicio < hora_fim)',
            name='ck_filial_horarios_intervalo',
        ),
        schema='public',
    )


def downgrade():
    op.drop_table('filial_horarios', schema='public')
