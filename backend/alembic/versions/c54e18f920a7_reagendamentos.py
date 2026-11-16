"""Reagendamento com auditoria imutável e propagação do profissional na comanda."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c54e18f920a7'
down_revision = 'ab47d12e903f'
branch_labels = depends_on = None


def _contexto(onupdate=None):
    op.drop_constraint('fk_comandas_contexto_agendamento', 'comandas', type_='foreignkey', schema='public')
    op.create_foreign_key('fk_comandas_contexto_agendamento', 'comandas', 'agendamentos',
        ['agendamento_id', 'filial_id', 'cliente_id', 'barbeiro_id'],
        ['id', 'filial_id', 'cliente_id', 'barbeiro_id'],
        source_schema='public', referent_schema='public', onupdate=onupdate)


def upgrade():
    op.execute('LOCK TABLE public.agendamentos, public.comandas IN ACCESS EXCLUSIVE MODE')
    _contexto('CASCADE')
    op.create_table('reagendamentos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agendamento_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.agendamentos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_por', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), server_default=sa.text('clock_timestamp()'), nullable=False),
        sa.Column('motivo', sa.String(1000), nullable=True),
        sa.Column('data_anterior', sa.Date(), nullable=False),
        sa.Column('hora_inicio_anterior', sa.Time(), nullable=False),
        sa.Column('hora_fim_anterior', sa.Time(), nullable=False),
        sa.Column('barbeiro_id_anterior', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('data_nova', sa.Date(), nullable=False),
        sa.Column('hora_inicio_nova', sa.Time(), nullable=False),
        sa.Column('hora_fim_nova', sa.Time(), nullable=False),
        sa.Column('barbeiro_id_novo', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.CheckConstraint('hora_fim_anterior > hora_inicio_anterior', name='ck_reagendamento_anterior'),
        sa.CheckConstraint('hora_fim_nova > hora_inicio_nova', name='ck_reagendamento_novo'), schema='public')
    op.create_index('ix_reagendamentos_reserva_registro', 'reagendamentos', ['agendamento_id', 'registrado_em'], schema='public')
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
    op.execute('ALTER TABLE public.reagendamentos ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL PRIVILEGES ON TABLE public.reagendamentos FROM PUBLIC')
    # Revoga concessões materializadas pelos defaults do criador, inclusive
    # grants por coluna. Não altera default privileges nem qualquer outra tabela.
    op.execute("""
        DO $$ DECLARE alvo text; coluna text;
        BEGIN
            FOREACH alvo IN ARRAY ARRAY['PUBLIC','anon','authenticated','service_role','relaxabarber_runtime']
            LOOP
                IF alvo='PUBLIC' OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                    IF alvo <> 'PUBLIC' THEN
                        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.reagendamentos FROM %I', alvo);
                    END IF;
                    FOR coluna IN SELECT attname FROM pg_attribute
                        WHERE attrelid='public.reagendamentos'::regclass
                          AND attnum>0 AND NOT attisdropped
                    LOOP
                        EXECUTE format('REVOKE ALL PRIVILEGES (%I) ON TABLE public.reagendamentos FROM %s',
                                       coluna, CASE WHEN alvo='PUBLIC' THEN 'PUBLIC' ELSE quote_ident(alvo) END);
                    END LOOP;
                END IF;
            END LOOP;
        END $$
    """)
    op.execute('GRANT SELECT, INSERT ON TABLE public.reagendamentos TO relaxabarber_runtime')
    op.execute("""
        DO $$ DECLARE alvo text;
        BEGIN
            FOREACH alvo IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=alvo) THEN
                    IF has_any_column_privilege(alvo,'public.reagendamentos','SELECT')
                       OR has_any_column_privilege(alvo,'public.reagendamentos','INSERT')
                       OR has_any_column_privilege(alvo,'public.reagendamentos','UPDATE')
                       OR has_any_column_privilege(alvo,'public.reagendamentos','REFERENCES')
                       OR has_table_privilege(alvo,'public.reagendamentos','DELETE')
                       OR has_table_privilege(alvo,'public.reagendamentos','TRUNCATE')
                       OR has_table_privilege(alvo,'public.reagendamentos','TRIGGER') THEN
                        RAISE EXCEPTION 'Papel % ainda possui acesso efetivo herdado; revise memberships', alvo;
                    END IF;
                    IF current_setting('server_version_num')::integer >= 170000 THEN
                        IF has_table_privilege(alvo,'public.reagendamentos','MAINTAIN') THEN
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
            IF has_any_column_privilege('relaxabarber_runtime','public.reagendamentos','UPDATE')
               OR has_any_column_privilege('relaxabarber_runtime','public.reagendamentos','REFERENCES')
               OR has_table_privilege('relaxabarber_runtime','public.reagendamentos','TRUNCATE')
               OR has_table_privilege('relaxabarber_runtime','public.reagendamentos','TRIGGER')
               OR pg_has_role('relaxabarber_runtime',
                    (SELECT relowner FROM pg_class WHERE oid='public.reagendamentos'::regclass), 'USAGE')
            THEN
                RAISE EXCEPTION 'Runtime possui privilegios herdados incompativeis com menor privilegio';
            END IF;
            IF current_setting('server_version_num')::integer >= 170000 THEN
                IF has_table_privilege('relaxabarber_runtime','public.reagendamentos','MAINTAIN') THEN
                    RAISE EXCEPTION 'Runtime possui MAINTAIN herdado';
                END IF;
            END IF;
        END $$
    """)
    op.execute('CREATE POLICY reagendamentos_runtime_select ON public.reagendamentos FOR SELECT TO relaxabarber_runtime USING (true)')
    op.execute('CREATE POLICY reagendamentos_runtime_insert ON public.reagendamentos FOR INSERT TO relaxabarber_runtime WITH CHECK (true)')



    op.execute("""DO $$ BEGIN
        IF has_table_privilege('relaxabarber_runtime','public.reagendamentos','DELETE') THEN
            RAISE EXCEPTION 'Runtime nao pode remover historico de reagendamento';
        END IF;
    END $$""")
    op.execute("""CREATE FUNCTION public.reagendamento_impedir_mutacao() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog AS $$ BEGIN
            RAISE EXCEPTION 'Historico de reagendamentos e imutavel';
        END $$""")
    op.execute('REVOKE ALL ON FUNCTION public.reagendamento_impedir_mutacao() FROM PUBLIC')
    op.execute('CREATE TRIGGER reagendamento_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.reagendamentos FOR EACH STATEMENT EXECUTE FUNCTION public.reagendamento_impedir_mutacao()')
    op.execute('GRANT UPDATE (data, hora_inicio, hora_fim, barbeiro_id) ON public.agendamentos TO relaxabarber_runtime')


def downgrade():
    op.execute('LOCK TABLE public.agendamentos, public.comandas, public.reagendamentos IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.reagendamentos) THEN
        RAISE EXCEPTION 'Downgrade bloqueado: ha historico de reagendamento a preservar';
    END IF; END $$""")
    op.execute('REVOKE UPDATE (data, hora_inicio, hora_fim, barbeiro_id) ON public.agendamentos FROM relaxabarber_runtime')
    op.drop_table('reagendamentos', schema='public')
    op.execute('DROP FUNCTION public.reagendamento_impedir_mutacao()')
    _contexto()