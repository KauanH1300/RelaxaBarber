"""Torna contexto obrigatório e garante coerência de profissional/comanda.

Revision ID: a15c39d42e68
Revises: f04b28c31d57
Preserva integralmente a EXCLUDE global e demais constraints da Fase 1.
"""
from alembic import op
import sqlalchemy as sa

revision = "a15c39d42e68"
down_revision = "f04b28c31d57"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("LOCK TABLE public.agendamentos, public.comandas IN ACCESS EXCLUSIVE MODE"))
    invalidos = conn.scalar(sa.text("""
        SELECT (SELECT count(*) FROM public.agendamentos a
          LEFT JOIN public.filiais f ON f.id=a.filial_id
          LEFT JOIN public.usuario_filiais v ON v.usuario_id=a.barbeiro_id AND v.filial_id=a.filial_id
          WHERE f.id IS NULL OR v.id IS NULL)
        + (SELECT count(*) FROM public.comandas c LEFT JOIN public.agendamentos a ON a.id=c.agendamento_id
          WHERE a.id IS NULL OR c.filial_id IS DISTINCT FROM a.filial_id
          OR c.cliente_id IS DISTINCT FROM a.cliente_id OR c.barbeiro_id IS DISTINCT FROM a.barbeiro_id)
    """))
    if invalidos:
        raise RuntimeError("Contexto de filial inválido; restrições não corrigem dados")
    for table in ("agendamentos", "comandas"):
        op.alter_column(table, "filial_id", nullable=False, schema="public")
        op.create_foreign_key(f"fk_{table}_filial", table, "filiais", ["filial_id"], ["id"], source_schema="public", referent_schema="public")
    op.create_foreign_key("fk_agendamentos_profissional_filial", "agendamentos", "usuario_filiais", ["barbeiro_id", "filial_id"], ["usuario_id", "filial_id"], source_schema="public", referent_schema="public")
    op.create_unique_constraint("uq_agendamentos_contexto", "agendamentos", ["id", "filial_id", "cliente_id", "barbeiro_id"], schema="public")
    op.create_foreign_key("fk_comandas_contexto_agendamento", "comandas", "agendamentos", ["agendamento_id", "filial_id", "cliente_id", "barbeiro_id"], ["id", "filial_id", "cliente_id", "barbeiro_id"], source_schema="public", referent_schema="public")
    op.create_index("ix_agendamentos_filial_data_inicio", "agendamentos", ["filial_id", "data", "hora_inicio"], schema="public")
    op.create_index("ix_comandas_filial_status", "comandas", ["filial_id", "status"], schema="public")


def downgrade():
    raise NotImplementedError("Não remover garantias de filial sem plano explícito de recuperação")
