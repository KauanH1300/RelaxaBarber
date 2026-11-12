"""RLS e menor privilégio somente em public.filial_horarios.

Revision ID: c82f6a1d904b
Revises: b91e4c7d203a

Pré-requisito: relaxabarber_runtime provisionado fora das migrações.
Downgrade fail-closed: preserva dados, RLS e revogações dos papéis externos;
remove policies e acesso do runtime. Não restaura grants potencialmente inseguros
nem defaults globais. O runtime deixa de operar o expediente até novo upgrade.
"""
from alembic import op

revision = 'c82f6a1d904b'
down_revision = 'b91e4c7d203a'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='relaxabarber_runtime') THEN
                RAISE EXCEPTION 'Papel relaxabarber_runtime ausente; provisione-o antes da migracao';
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='relaxabarber_runtime'
                       AND (rolsuper OR rolbypassrls)) THEN
                RAISE EXCEPTION 'relaxabarber_runtime nao pode possuir SUPERUSER ou BYPASSRLS';
            END IF;
        END $$
    """)
    op.execute('ALTER TABLE public.filial_horarios ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL PRIVILEGES ON TABLE public.filial_horarios FROM PUBLIC')
    # Revoga concessões materializadas pelos defaults do criador, inclusive
    # grants por coluna. Não altera default privileges nem qualquer outra tabela.
    op.execute("""
        DO $$ DECLARE alvo text; coluna text;
        BEGIN
            FOREACH alvo IN ARRAY ARRAY['PUBLIC','anon','authenticated','service_role','relaxabarber_runtime']
            LOOP
                IF alvo='PUBLIC' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                    IF alvo <> 'PUBLIC' THEN
                        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.filial_horarios FROM %I', alvo);
                    END IF;
                    FOR coluna IN SELECT attname FROM pg_attribute
                        WHERE attrelid='public.filial_horarios'::regclass
                          AND attnum>0 AND NOT attisdropped
                    LOOP
                        EXECUTE format('REVOKE ALL PRIVILEGES (%I) ON TABLE public.filial_horarios FROM %s',
                                       coluna, CASE WHEN alvo='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(alvo) END);
                    END LOOP;
                END IF;
            END LOOP;
        END $$
    """)
    op.execute('GRANT SELECT, INSERT, DELETE ON TABLE public.filial_horarios TO relaxabarber_runtime')
    op.execute("""
        DO $$ DECLARE alvo text;
        BEGIN
            FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                    IF has_any_column_privilege(alvo,'public.filial_horarios','SELECT')
                       OR has_any_column_privilege(alvo,'public.filial_horarios','INSERT')
                       OR has_any_column_privilege(alvo,'public.filial_horarios','UPDATE')
                       OR has_any_column_privilege(alvo,'public.filial_horarios','REFERENCES')
                       OR has_table_privilege(alvo,'public.filial_horarios','DELETE')
                       OR has_table_privilege(alvo,'public.filial_horarios','TRUNCATE')
                       OR has_table_privilege(alvo,'public.filial_horarios','TRIGGER') THEN
                        RAISE EXCEPTION 'Papel % ainda possui acesso efetivo herdado; revise memberships', alvo;
                    END IF;
                    IF current_setting('server_version_num')::integer >= 170000 THEN
                        IF has_table_privilege(alvo,'public.filial_horarios','MAINTAIN') THEN
                            RAISE EXCEPTION 'Papel % ainda possui MAINTAIN herdado', alvo;
                        END IF;
                    END IF;
                END IF;
            END LOOP;
        END $$
    """)
    # Falha também se memberships ou grants de terceiros ainda ampliarem o runtime.
    op.execute("""
        DO $$ BEGIN
            IF has_any_column_privilege('relaxabarber_runtime','public.filial_horarios','UPDATE')
               OR has_any_column_privilege('relaxabarber_runtime','public.filial_horarios','REFERENCES')
               OR has_table_privilege('relaxabarber_runtime','public.filial_horarios','TRUNCATE')
               OR has_table_privilege('relaxabarber_runtime','public.filial_horarios','TRIGGER')
               OR pg_has_role('relaxabarber_runtime',
                    (SELECT relowner FROM pg_class WHERE oid='public.filial_horarios'::regclass), 'USAGE')
            THEN
                RAISE EXCEPTION 'Runtime possui privilegios herdados incompativeis com menor privilegio';
            END IF;
            IF current_setting('server_version_num')::integer >= 170000 THEN
                IF has_table_privilege('relaxabarber_runtime','public.filial_horarios','MAINTAIN') THEN
                    RAISE EXCEPTION 'Runtime possui MAINTAIN herdado';
                END IF;
            END IF;
        END $$
    """)
    op.execute('CREATE POLICY filial_horarios_runtime_select ON public.filial_horarios FOR SELECT TO relaxabarber_runtime USING (true)')
    op.execute('CREATE POLICY filial_horarios_runtime_insert ON public.filial_horarios FOR INSERT TO relaxabarber_runtime WITH CHECK (true)')
    op.execute('CREATE POLICY filial_horarios_runtime_delete ON public.filial_horarios FOR DELETE TO relaxabarber_runtime USING (true)')


def downgrade():
    # Intencionalmente não desabilitar RLS nem restabelecer acesso externo.
    for nome in ('select', 'insert', 'delete'):
        op.execute(f'DROP POLICY filial_horarios_runtime_{nome} ON public.filial_horarios')
    op.execute('REVOKE SELECT, INSERT, DELETE ON TABLE public.filial_horarios FROM relaxabarber_runtime')
