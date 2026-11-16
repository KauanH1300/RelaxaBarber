"""Jornada individual por filial e profissional."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'ab47d12e903f'
down_revision = 'e14a29bc7031'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('jornadas_barbeiros',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('filial_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.filiais.id'), nullable=False),
        sa.Column('barbeiro_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id'), nullable=False),
        sa.Column('configuracao', sa.JSON(), nullable=False),
        sa.UniqueConstraint('filial_id', 'barbeiro_id', name='uq_jornada_filial_barbeiro'), schema='public')
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
    op.execute('ALTER TABLE public.jornadas_barbeiros ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL PRIVILEGES ON TABLE public.jornadas_barbeiros FROM PUBLIC')
    # Revoga concessões materializadas pelos defaults do criador, inclusive
    # grants por coluna. Não altera default privileges nem qualquer outra tabela.
    op.execute("""
        DO $$ DECLARE alvo text; coluna text;
        BEGIN
            FOREACH alvo IN ARRAY ARRAY['PUBLIC','anon','authenticated','service_role','relaxabarber_runtime']
            LOOP
                IF alvo='PUBLIC' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                    IF alvo <> 'PUBLIC' THEN
                        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.jornadas_barbeiros FROM %I', alvo);
                    END IF;
                    FOR coluna IN SELECT attname FROM pg_attribute
                        WHERE attrelid='public.jornadas_barbeiros'::regclass
                          AND attnum>0 AND NOT attisdropped
                    LOOP
                        EXECUTE format('REVOKE ALL PRIVILEGES (%I) ON TABLE public.jornadas_barbeiros FROM %s',
                                       coluna, CASE WHEN alvo='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(alvo) END);
                    END LOOP;
                END IF;
            END LOOP;
        END $$
    """)
    op.execute('GRANT SELECT, INSERT, DELETE ON TABLE public.jornadas_barbeiros TO relaxabarber_runtime')
    op.execute("""
        DO $$ DECLARE alvo text;
        BEGIN
            FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                    IF has_any_column_privilege(alvo,'public.jornadas_barbeiros','SELECT')
                       OR has_any_column_privilege(alvo,'public.jornadas_barbeiros','INSERT')
                       OR has_any_column_privilege(alvo,'public.jornadas_barbeiros','UPDATE')
                       OR has_any_column_privilege(alvo,'public.jornadas_barbeiros','REFERENCES')
                       OR has_table_privilege(alvo,'public.jornadas_barbeiros','DELETE')
                       OR has_table_privilege(alvo,'public.jornadas_barbeiros','TRUNCATE')
                       OR has_table_privilege(alvo,'public.jornadas_barbeiros','TRIGGER') THEN
                        RAISE EXCEPTION 'Papel % ainda possui acesso efetivo herdado; revise memberships', alvo;
                    END IF;
                    IF current_setting('server_version_num')::integer >= 170000 THEN
                        IF has_table_privilege(alvo,'public.jornadas_barbeiros','MAINTAIN') THEN
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
            IF has_any_column_privilege('relaxabarber_runtime','public.jornadas_barbeiros','UPDATE')
               OR has_any_column_privilege('relaxabarber_runtime','public.jornadas_barbeiros','REFERENCES')
               OR has_table_privilege('relaxabarber_runtime','public.jornadas_barbeiros','TRUNCATE')
               OR has_table_privilege('relaxabarber_runtime','public.jornadas_barbeiros','TRIGGER')
               OR pg_has_role('relaxabarber_runtime',
                    (SELECT relowner FROM pg_class WHERE oid='public.jornadas_barbeiros'::regclass), 'USAGE')
            THEN
                RAISE EXCEPTION 'Runtime possui privilegios herdados incompativeis com menor privilegio';
            END IF;
            IF current_setting('server_version_num')::integer >= 170000 THEN
                IF has_table_privilege('relaxabarber_runtime','public.jornadas_barbeiros','MAINTAIN') THEN
                    RAISE EXCEPTION 'Runtime possui MAINTAIN herdado';
                END IF;
            END IF;
        END $$
    """)
    op.execute('CREATE POLICY jornadas_barbeiros_runtime_select ON public.jornadas_barbeiros FOR SELECT TO relaxabarber_runtime USING (true)')
    op.execute('CREATE POLICY jornadas_barbeiros_runtime_insert ON public.jornadas_barbeiros FOR INSERT TO relaxabarber_runtime WITH CHECK (true)')
    op.execute('CREATE POLICY jornadas_barbeiros_runtime_delete ON public.jornadas_barbeiros FOR DELETE TO relaxabarber_runtime USING (true)')


def downgrade():
    op.drop_table('jornadas_barbeiros', schema='public')
