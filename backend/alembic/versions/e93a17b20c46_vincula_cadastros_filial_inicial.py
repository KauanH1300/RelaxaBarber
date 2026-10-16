"""Bootstrap único: cadastros existentes vinculados somente à filial inicial.

Revision ID: e93a17b20c46
Revises: d82f06a19b35
Sem triggers, pagamentos ou atualização de registros legados.
"""
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = "e93a17b20c46"
down_revision = "d82f06a19b35"
branch_labels = None
depends_on = None

EMPRESA_ID = UUID("f1238845-0d47-4fb1-882f-566fbcd09ef0")
FILIAL_INICIAL_ID = UUID("97fa517c-d7d7-4e97-a9ea-e332699918fd")
VINCULOS_NAMESPACE = UUID("a3056bb7-92f2-47ba-9383-cd9f31e23703")


def upgrade():
    conn = op.get_bind()
    # Esta revisão é um bootstrap, não uma rotina de sincronização/reexecução.
    # Bloqueia escritas legadas durante o snapshot; aplicação futura exige janela.
    conn.execute(sa.text("LOCK TABLE public.usuarios, public.clientes IN SHARE MODE"))
    conn.execute(sa.text("LOCK TABLE public.empresas, public.filiais, public.usuario_filiais, public.cliente_filiais IN EXCLUSIVE MODE"))
    for table in ("empresas", "filiais", "usuario_filiais", "cliente_filiais"):
        if conn.scalar(sa.text(f"SELECT count(*) FROM public.{table}")):
            raise RuntimeError("Bootstrap de filial exige tabelas novas vazias; nenhuma associação será presumida")
    conn.execute(sa.text("INSERT INTO public.empresas (id,nome) VALUES (:id,'RelaxaBarber')"), {"id": EMPRESA_ID})
    conn.execute(sa.text("INSERT INTO public.filiais (id,empresa_id,nome) VALUES (:id,:empresa,'Filial inicial')"), {"id": FILIAL_INICIAL_ID, "empresa": EMPRESA_ID})
    # UUIDs dos vínculos determinísticos, sem depender de extensões PostgreSQL.
    # Lotes limitados; nenhum dado pessoal ou credencial é selecionado.
    for table, source, key in (("usuario_filiais", "usuarios", "usuario_id"), ("cliente_filiais", "clientes", "cliente_id")):
        last = None
        while True:
            query = f"SELECT id{', ativo' if source == 'usuarios' else ''} FROM public.{source}"
            params = {}
            if last is not None:
                query += " WHERE id > :last"
                params["last"] = last
            rows = conn.execute(sa.text(query + " ORDER BY id LIMIT 1000"), params).mappings().all()
            if not rows:
                break
            values = [{"id": uuid5(VINCULOS_NAMESPACE, f"{source}:{row['id']}:{FILIAL_INICIAL_ID}"), "origem": row["id"], "filial": FILIAL_INICIAL_ID, **({"ativo": row["ativo"]} if source == "usuarios" else {})} for row in rows]
            columns = f"id,{key},filial_id" + (",ativo" if source == "usuarios" else "")
            placeholders = ":id,:origem,:filial" + (",:ativo" if source == "usuarios" else "")
            conn.execute(sa.text(f"INSERT INTO public.{table} ({columns}) VALUES ({placeholders})"), values)
            last = rows[-1]["id"]
    missing = conn.scalar(sa.text("""
        SELECT (SELECT count(*) FROM public.usuarios u LEFT JOIN public.usuario_filiais v
          ON v.usuario_id=u.id AND v.filial_id=:filial WHERE v.id IS NULL OR v.ativo IS DISTINCT FROM u.ativo)
        + (SELECT count(*) FROM public.clientes c LEFT JOIN public.cliente_filiais v
          ON v.cliente_id=c.id AND v.filial_id=:filial WHERE v.id IS NULL)
    """), {"filial": FILIAL_INICIAL_ID})
    if missing:
        raise RuntimeError("Backfill de vínculos incompleto; transação deve ser revertida")


def downgrade():
    raise NotImplementedError("Bootstrap contém vínculos históricos; reversão exige plano explícito e não apaga dados automaticamente")
