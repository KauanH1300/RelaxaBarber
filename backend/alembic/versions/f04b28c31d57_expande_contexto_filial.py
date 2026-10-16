"""Expande contexto e associa históricos exclusivamente à filial inicial.

Revision ID: f04b28c31d57
Revises: e93a17b20c46
Exige janela sem escritas. Não altera ClienteFilial nem dados financeiros.
"""
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = "f04b28c31d57"
down_revision = "e93a17b20c46"
branch_labels = None
depends_on = None

FILIAL_INICIAL_ID = UUID("97fa517c-d7d7-4e97-a9ea-e332699918fd")
VINCULOS_NAMESPACE = UUID("a3056bb7-92f2-47ba-9383-cd9f31e23703")


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("LOCK TABLE public.empresas, public.filiais, public.usuarios, public.usuario_filiais, public.agendamentos, public.comandas IN ACCESS EXCLUSIVE MODE"))
    unidades = conn.execute(sa.text("SELECT id FROM public.filiais")).scalars().all()
    if unidades != [FILIAL_INICIAL_ID]:
        raise RuntimeError("Backfill exige somente a filial inicial conhecida; nenhuma unidade será presumida")
    divergencias = conn.scalar(sa.text("""
        SELECT count(*) FROM public.comandas c LEFT JOIN public.agendamentos a ON a.id=c.agendamento_id
        WHERE a.id IS NULL OR c.cliente_id IS DISTINCT FROM a.cliente_id
        OR c.barbeiro_id IS DISTINCT FROM a.barbeiro_id
    """))
    if divergencias:
        raise RuntimeError("Comandas e agendamentos divergentes; backfill não repara históricos")
    # Cadastros criados entre A e B: completa somente vínculos ausentes.
    # Um vínculo já inativo jamais é reativado pela migration.
    last = None
    while True:
        query = """SELECT u.id,u.ativo FROM public.usuarios u WHERE NOT EXISTS (
            SELECT 1 FROM public.usuario_filiais v WHERE v.usuario_id=u.id AND v.filial_id=:filial)
        """
        params = {"filial": FILIAL_INICIAL_ID}
        if last is not None:
            query += " AND u.id > :last"
            params["last"] = last
        rows = conn.execute(sa.text(query + " ORDER BY u.id LIMIT 1000"), params).mappings().all()
        if not rows:
            break
        conn.execute(sa.text("INSERT INTO public.usuario_filiais(id,usuario_id,filial_id,ativo) VALUES (:id,:usuario,:filial,:ativo)"), [
            {"id": uuid5(VINCULOS_NAMESPACE, f"usuarios:{r['id']}:{FILIAL_INICIAL_ID}"), "usuario": r["id"], "filial": FILIAL_INICIAL_ID, "ativo": r["ativo"]} for r in rows
        ])
        last = rows[-1]["id"]
    op.add_column("agendamentos", sa.Column("filial_id", sa.UUID(), nullable=True), schema="public")
    op.add_column("comandas", sa.Column("filial_id", sa.UUID(), nullable=True), schema="public")
    conn.execute(sa.text("UPDATE public.agendamentos SET filial_id=:filial"), {"filial": FILIAL_INICIAL_ID})
    conn.execute(sa.text("UPDATE public.comandas c SET filial_id=a.filial_id FROM public.agendamentos a WHERE a.id=c.agendamento_id"))


def downgrade():
    raise NotImplementedError("Contexto histórico de filial exige plano explícito de recuperação")
