"""Persistência financeira aditiva, sem backfill nem mudança operacional.

Revision ID: d93a7e2f610c
Revises: c82f6a1d904b
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d93a7e2f610c"
down_revision = "c82f6a1d904b"
branch_labels = None
depends_on = None

TABELAS = ("controles_financeiros_comanda", "pagamentos_comanda",
           "estornos_pagamento", "fechamentos_financeiros_comanda")


def contexto():
    return [sa.Column("comanda_id", UUID(as_uuid=True), nullable=False),
            sa.Column("filial_id", UUID(as_uuid=True), nullable=False)]


def auditoria(fk):
    return [sa.Column("registrado_em", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.text("now()")),
            sa.Column("registrado_por", UUID(as_uuid=True), nullable=False),
            sa.ForeignKeyConstraint(["registrado_por"], ["public.usuarios.id"],
                                    name=fk, ondelete="RESTRICT")]


def idempotencia(prefixo):
    return [sa.Column("chave_idempotencia", UUID(as_uuid=True), nullable=False),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.CheckConstraint("length(fingerprint) = 64", name=f"ck_{prefixo}_fingerprint")]


def fk_controle(nome):
    return sa.ForeignKeyConstraint(["comanda_id", "filial_id"],
        ["public.controles_financeiros_comanda.comanda_id", "public.controles_financeiros_comanda.filial_id"],
        name=nome, ondelete="RESTRICT")


def upgrade():
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='relaxabarber_runtime'
                       AND NOT rolsuper AND NOT rolbypassrls) THEN
            RAISE EXCEPTION 'relaxabarber_runtime ausente ou privilegiado';
        END IF;
    END $$""")
    op.create_unique_constraint("uq_comandas_id_filial", "comandas", ["id", "filial_id"], schema="public")
    op.create_table("controles_financeiros_comanda", *contexto(),
        *auditoria("fk_controle_financeiro_responsavel"), sa.Column("motivo", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("comanda_id"),
        sa.UniqueConstraint("comanda_id", "filial_id", name="uq_controle_financeiro_contexto"),
        sa.ForeignKeyConstraint(["comanda_id", "filial_id"], ["public.comandas.id", "public.comandas.filial_id"],
                                name="fk_controle_financeiro_comanda", ondelete="RESTRICT"),
        sa.CheckConstraint("length(trim(motivo)) > 0", name="ck_controle_financeiro_motivo"), schema="public")
    op.create_table("pagamentos_comanda",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), *contexto(),
        sa.Column("valor", sa.Numeric(10, 2), nullable=False),
        sa.Column("forma", sa.String(10), nullable=False),
        sa.Column("recebido_em", sa.DateTime(timezone=True), nullable=False),
        *auditoria("fk_pagamento_responsavel"), *idempotencia("pagamento"),
        fk_controle("fk_pagamento_controle"),
        sa.UniqueConstraint("id", "comanda_id", "filial_id", name="uq_pagamento_contexto"),
        sa.UniqueConstraint("comanda_id", "chave_idempotencia", name="uq_pagamento_idempotencia"),
        sa.CheckConstraint("valor > 0 AND valor <= 99999999.99", name="ck_pagamento_valor"),
        sa.CheckConstraint("forma IN ('dinheiro','pix','debito','credito')", name="ck_pagamento_forma"), schema="public")
    op.create_index("ix_pagamentos_filial_recebido", "pagamentos_comanda", ["filial_id", "recebido_em"], schema="public")
    op.create_table("estornos_pagamento",
        sa.Column("id", UUID(as_uuid=True), primary_key=True), *contexto(),
        sa.Column("pagamento_id", UUID(as_uuid=True), nullable=False),
        sa.Column("valor", sa.Numeric(10, 2), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=False),
        sa.Column("efetivado_em", sa.DateTime(timezone=True), nullable=False),
        *auditoria("fk_estorno_responsavel"), *idempotencia("estorno"),
        sa.ForeignKeyConstraint(["pagamento_id", "comanda_id", "filial_id"],
            ["public.pagamentos_comanda.id", "public.pagamentos_comanda.comanda_id", "public.pagamentos_comanda.filial_id"],
            name="fk_estorno_pagamento_contexto", ondelete="RESTRICT"),
        sa.UniqueConstraint("comanda_id", "chave_idempotencia", name="uq_estorno_idempotencia"),
        sa.CheckConstraint("valor > 0 AND valor <= 99999999.99", name="ck_estorno_valor"),
        sa.CheckConstraint("length(trim(motivo)) > 0", name="ck_estorno_motivo"), schema="public")
    op.create_index("ix_estornos_pagamento", "estornos_pagamento", ["pagamento_id"], schema="public")
    op.create_index("ix_estornos_filial_efetivo", "estornos_pagamento", ["filial_id", "efetivado_em"], schema="public")
    op.create_table("fechamentos_financeiros_comanda", *contexto(),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        sa.Column("recebido_liquido", sa.Numeric(10, 2), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        *auditoria("fk_fechamento_responsavel"), *idempotencia("fechamento"),
        sa.PrimaryKeyConstraint("comanda_id"), fk_controle("fk_fechamento_controle"),
        sa.CheckConstraint("total >= 0 AND total <= 99999999.99", name="ck_fechamento_total"),
        sa.CheckConstraint("recebido_liquido >= 0 AND recebido_liquido <= 99999999.99", name="ck_fechamento_recebido"),
        sa.CheckConstraint("total = recebido_liquido", name="ck_fechamento_quitacao"),
        sa.CheckConstraint("total <> 0 OR (motivo IS NOT NULL AND length(trim(motivo)) > 0)",
                           name="ck_fechamento_zero_motivo"), schema="public")
    op.create_index("ix_fechamentos_filial_registro", "fechamentos_financeiros_comanda", ["filial_id", "registrado_em"], schema="public")

    # Invoker e search_path fechado: não ampliam privilégios do chamador.
    op.execute("""CREATE FUNCTION public.financeiro_carimbar_registro() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
            NEW.registrado_em := clock_timestamp();
            IF TG_TABLE_NAME='pagamentos_comanda' THEN
                IF NOT isfinite(NEW.recebido_em) THEN
                    RAISE EXCEPTION 'Data efetiva deve ser finita' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME='estornos_pagamento' THEN
                IF NOT isfinite(NEW.efetivado_em) THEN
                    RAISE EXCEPTION 'Data efetiva deve ser finita' USING ERRCODE='23514';
                END IF;
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE FUNCTION public.financeiro_impedir_mutacao() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
            RAISE EXCEPTION 'Historico financeiro imutavel: use lancamento compensatorio'
                USING ERRCODE='23514';
        END $$""")
    for funcao in ("financeiro_carimbar_registro", "financeiro_impedir_mutacao"):
        op.execute(f"REVOKE ALL ON FUNCTION public.{funcao}() FROM PUBLIC")
    for tabela in TABELAS:
        op.execute(f"CREATE TRIGGER financeiro_carimbo BEFORE INSERT ON public.{tabela} FOR EACH ROW EXECUTE FUNCTION public.financeiro_carimbar_registro()")
        op.execute(f"CREATE TRIGGER financeiro_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.{tabela} FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()")
        proteger_tabela(tabela)


def proteger_tabela(tabela):
    # Remover inclusive ACLs por coluna que event triggers/defaults possam criar.
    op.execute(f"ALTER TABLE public.{tabela} ENABLE ROW LEVEL SECURITY")
    op.execute(f"""DO $$ DECLARE alvo text; coluna text; BEGIN
        FOREACH alvo IN ARRAY ARRAY['PUBLIC','anon','authenticated','service_role','relaxabarber_runtime'] LOOP
            IF alvo='PUBLIC' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                EXECUTE format('REVOKE ALL ON TABLE public.{tabela} FROM %s',
                    CASE WHEN alvo='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(alvo) END);
                FOR coluna IN SELECT attname FROM pg_attribute
                    WHERE attrelid='public.{tabela}'::regclass AND attnum>0 AND NOT attisdropped LOOP
                    EXECUTE format('REVOKE ALL (%I) ON TABLE public.{tabela} FROM %s', coluna,
                        CASE WHEN alvo='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(alvo) END);
                END LOOP;
            END IF;
        END LOOP;
    END $$""")
    op.execute(f"GRANT SELECT, INSERT ON TABLE public.{tabela} TO relaxabarber_runtime")
    op.execute(f"CREATE POLICY financeiro_runtime_select ON public.{tabela} FOR SELECT TO relaxabarber_runtime USING (true)")
    op.execute(f"CREATE POLICY financeiro_runtime_insert ON public.{tabela} FOR INSERT TO relaxabarber_runtime WITH CHECK (true)")
    op.execute(f"""DO $$ DECLARE alvo text; priv text; BEGIN
        FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role','relaxabarber_runtime'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                FOREACH priv IN ARRAY ARRAY['SELECT','INSERT','UPDATE','REFERENCES'] LOOP
                    IF (alvo <> 'relaxabarber_runtime' OR priv NOT IN ('SELECT','INSERT'))
                       AND has_any_column_privilege(alvo,'public.{tabela}',priv) THEN
                        RAISE EXCEPTION 'Acesso efetivo herdado incompativel: %, %', alvo, priv;
                    END IF;
                END LOOP;
                FOREACH priv IN ARRAY ARRAY['DELETE','TRUNCATE','TRIGGER'] LOOP
                    IF has_table_privilege(alvo,'public.{tabela}',priv) THEN
                        RAISE EXCEPTION 'Acesso efetivo herdado incompativel: %, %', alvo, priv;
                    END IF;
                END LOOP;
                IF current_setting('server_version_num')::integer >= 170000 THEN
                    IF has_table_privilege(alvo,'public.{tabela}','MAINTAIN') THEN
                        RAISE EXCEPTION 'MAINTAIN herdado incompativel: %', alvo;
                    END IF;
                END IF;
            END IF;
        END LOOP;
        IF pg_has_role('relaxabarber_runtime',
            (SELECT relowner FROM pg_class WHERE oid='public.{tabela}'::regclass),'USAGE') THEN
            RAISE EXCEPTION 'Runtime herda o papel proprietario';
        END IF;
    END $$""")


def downgrade():
    # Impedir INSERT concorrente entre a verificação e a remoção.
    op.execute("LOCK TABLE " + ", ".join("public." + t for t in TABELAS) + " IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.controles_financeiros_comanda)
           OR EXISTS (SELECT 1 FROM public.pagamentos_comanda)
           OR EXISTS (SELECT 1 FROM public.estornos_pagamento)
           OR EXISTS (SELECT 1 FROM public.fechamentos_financeiros_comanda) THEN
            RAISE EXCEPTION 'Downgrade bloqueado: ha historico financeiro a preservar';
        END IF;
    END $$""")
    for tabela in reversed(TABELAS):
        op.drop_table(tabela, schema="public")
    op.execute("DROP FUNCTION public.financeiro_carimbar_registro()")
    op.execute("DROP FUNCTION public.financeiro_impedir_mutacao()")
    op.drop_constraint("uq_comandas_id_filial", "comandas", type_="unique", schema="public")
