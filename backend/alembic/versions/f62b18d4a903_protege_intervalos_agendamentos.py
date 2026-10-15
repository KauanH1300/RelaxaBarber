"""Protege intervalos e reservas concorrentes do mesmo profissional.

Revision ID: f62b18d4a903
Revises: c41a7e0b932d

Exige auditoria prévia e janela de aplicação: ADD EXCLUDE valida todos os
registros e adquire lock exclusivo. Não corrige ou cancela dados existentes.
"""
from alembic import op

revision = "f62b18d4a903"
down_revision = "c41a7e0b932d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public")
    # Supabase pode já ter a extensão em outro schema. Ajuste transacional do
    # search_path permite resolver suas operator classes sem mover a extensão.
    op.execute("""
        DO $$ DECLARE extension_schema text;
        BEGIN
            SELECT n.nspname INTO STRICT extension_schema
            FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
            WHERE e.extname = 'btree_gist';
            PERFORM set_config('search_path',
                'pg_catalog, public, ' || quote_ident(extension_schema), true);
        END $$
    """)
    op.create_check_constraint(
        "ck_agendamentos_intervalo_valido", "agendamentos",
        "hora_fim > hora_inicio", schema="public",
    )
    op.execute("""
        ALTER TABLE public.agendamentos
        ADD CONSTRAINT ex_agendamentos_profissional_periodo
        EXCLUDE USING gist (
            barbeiro_id WITH =,
            tsrange(data + hora_inicio, data + hora_fim, '[)') WITH &&
        ) WHERE (status <> 'cancelado') NOT DEFERRABLE
    """)


def downgrade() -> None:
    op.drop_constraint("ex_agendamentos_profissional_periodo", "agendamentos", schema="public")
    op.drop_constraint("ck_agendamentos_intervalo_valido", "agendamentos", schema="public")
    # A extensão pode ser compartilhada por outros objetos; não a remover.
