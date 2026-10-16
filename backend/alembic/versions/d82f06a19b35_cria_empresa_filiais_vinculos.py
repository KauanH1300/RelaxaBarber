"""Estrutura aditiva de empresa única, unidades e vínculos.

Revision ID: d82f06a19b35
Revises: a73d92bc6e14
Não altera tabelas operacionais nem ativa escopo de filial na API.
"""
from alembic import op
import sqlalchemy as sa

revision = "d82f06a19b35"
down_revision = "a73d92bc6e14"
branch_labels = None
depends_on = None


def timestamps():
    return [
        sa.Column("data_cadastro", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade():
    op.create_table(
        "empresas",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("singleton", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.CheckConstraint("singleton = 1", name="ck_empresas_singleton"),
        sa.UniqueConstraint("singleton", name="uq_empresas_singleton"),
        schema="public",
    )
    op.create_table(
        "filiais",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("empresa_id", sa.UUID(), nullable=False),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fuso_horario", sa.String(64), nullable=False, server_default=sa.text("'America/Recife'")),
        *timestamps(),
        sa.ForeignKeyConstraint(["empresa_id"], ["public.empresas.id"], name="fk_filiais_empresa"),
        sa.CheckConstraint("fuso_horario = 'America/Recife'", name="ck_filiais_fuso_horario"),
        schema="public",
    )
    op.create_index("ix_filiais_empresa_id", "filiais", ["empresa_id"], schema="public")
    op.create_table(
        "usuario_filiais",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("filial_id", sa.UUID(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        *timestamps(),
        sa.ForeignKeyConstraint(["usuario_id"], ["public.usuarios.id"], name="fk_usuario_filiais_usuario"),
        sa.ForeignKeyConstraint(["filial_id"], ["public.filiais.id"], name="fk_usuario_filiais_filial"),
        sa.UniqueConstraint("usuario_id", "filial_id", name="uq_usuario_filiais_usuario_filial"),
        schema="public",
    )
    op.create_index("ix_usuario_filiais_filial_id", "usuario_filiais", ["filial_id"], schema="public")
    op.create_table(
        "cliente_filiais",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("cliente_id", sa.UUID(), nullable=False),
        sa.Column("filial_id", sa.UUID(), nullable=False),
        sa.Column("data_cadastro", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["cliente_id"], ["public.clientes.id"], name="fk_cliente_filiais_cliente"),
        sa.ForeignKeyConstraint(["filial_id"], ["public.filiais.id"], name="fk_cliente_filiais_filial"),
        sa.UniqueConstraint("cliente_id", "filial_id", name="uq_cliente_filiais_cliente_filial"),
        schema="public",
    )
    op.create_index("ix_cliente_filiais_filial_id", "cliente_filiais", ["filial_id"], schema="public")


def downgrade():
    # Não apagar unidades/vínculos que possam ter adquirido significado operacional.
    raise NotImplementedError("Remoção de filiais e vínculos exige plano de recuperação explícito; downgrade destrutivo recusado")
