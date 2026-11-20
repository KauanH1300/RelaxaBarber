"""Bloqueios auditados e antecedência por filial."""
from alembic import op
import sqlalchemy as sa

revision = 'c74f21e6a930'
down_revision = 'b83e71a3c921'
LIMITES = {
    'antecedencia_reserva_horas': (0, 87600),
    'antecedencia_maxima_reserva_dias': (1, 3650),
    'antecedencia_cancelamento_horas': (0, 87600),
}
CHECK_JANELA = 'ck_filiais_janela_reserva'


def upgrade():
    for nome, (minimo, maximo) in LIMITES.items():
        opcional = nome == 'antecedencia_maxima_reserva_dias'
        op.add_column('filiais', sa.Column(
            nome, sa.Integer(), nullable=opcional, server_default=None if opcional else '0',
        ), schema='public')
        op.create_check_constraint(
            f'ck_filiais_{nome}', 'filiais', f'{nome} BETWEEN {minimo} AND {maximo}', schema='public',
        )
    op.create_check_constraint(CHECK_JANELA, 'filiais',
        'antecedencia_reserva_horas < antecedencia_maxima_reserva_dias * 24', schema='public')
    op.create_table('bloqueios_agenda',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('filial_id', sa.Uuid(), sa.ForeignKey('public.filiais.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('barbeiro_id', sa.Uuid(), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('hora_inicio', sa.Time(), nullable=False),
        sa.Column('hora_fim', sa.Time(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('criado_por', sa.Uuid(), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('revogado_por', sa.Uuid(), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT')),
        sa.Column('revogado_em', sa.DateTime(timezone=True)),
        sa.CheckConstraint('hora_inicio < hora_fim', name='ck_bloqueio_intervalo'),
        sa.CheckConstraint('length(trim(motivo)) BETWEEN 1 AND 1000', name='ck_bloqueio_motivo'),
        sa.CheckConstraint('(revogado_por IS NULL) = (revogado_em IS NULL)', name='ck_bloqueio_revogacao'),
        schema='public',
    )
    op.create_index('ix_bloqueios_agenda_contexto', 'bloqueios_agenda', ['filial_id','barbeiro_id','data'], schema='public')
    op.execute("""DO $$
        DECLARE
            caminho text := current_setting('search_path');
            schema_gist text;
        BEGIN
            SELECT n.nspname INTO STRICT schema_gist
            FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
            WHERE e.extname = 'btree_gist';
            PERFORM set_config('search_path', 'pg_catalog, public, ' || quote_ident(schema_gist), true);
            ALTER TABLE public.bloqueios_agenda ADD CONSTRAINT ex_bloqueios_agenda_intervalo
                EXCLUDE USING gist (filial_id WITH =, barbeiro_id WITH =,
                    tsrange(data + hora_inicio, data + hora_fim, '[)') WITH &&)
                WHERE (revogado_em IS NULL);
            PERFORM set_config('search_path', caminho, true);
        END $$""")
    op.execute('ALTER TABLE public.bloqueios_agenda ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON public.bloqueios_agenda FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
    for acao, condicao in (('SELECT','USING (true)'), ('INSERT','WITH CHECK (true)'), ('UPDATE','USING (revogado_em IS NULL) WITH CHECK (revogado_em IS NOT NULL)')):
        op.execute(f'CREATE POLICY bloqueio_runtime_{acao.lower()} ON public.bloqueios_agenda FOR {acao} TO relaxabarber_runtime {condicao}')
    op.execute('GRANT SELECT, INSERT ON public.bloqueios_agenda TO relaxabarber_runtime')
    op.execute('GRANT UPDATE (revogado_por, revogado_em) ON public.bloqueios_agenda TO relaxabarber_runtime')
    op.execute(f'GRANT UPDATE ({", ".join(LIMITES)}) ON public.filiais TO relaxabarber_runtime')

    # Mesma chave por filial/profissional/dia. Agendamentos usam lock compartilhado
    # e continuam concorrendo entre si pela EXCLUDE já existente.
    op.execute("""CREATE FUNCTION public.validar_ocupacao_agenda() RETURNS trigger
        LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
        DECLARE chave bigint;
        BEGIN
            chave := hashtextextended('agenda:' || NEW.filial_id || ':' || NEW.barbeiro_id || ':' || (NEW.data - DATE '2000-01-01'), 0);
            IF TG_TABLE_NAME = 'agendamentos' THEN
                IF NEW.status IN ('cancelado','nao_compareceu') THEN RETURN NEW; END IF;
                PERFORM pg_advisory_xact_lock_shared(chave);
                IF EXISTS (SELECT 1 FROM public.bloqueios_agenda b WHERE b.filial_id=NEW.filial_id
                    AND b.barbeiro_id=NEW.barbeiro_id AND b.data=NEW.data AND b.revogado_em IS NULL
                    AND b.hora_inicio<NEW.hora_fim AND b.hora_fim>NEW.hora_inicio) THEN
                    RAISE EXCEPTION 'Horário bloqueado na agenda'
                        USING ERRCODE='23P01', CONSTRAINT='ex_agenda_conflito_bloqueio';
                END IF;
            ELSE
                PERFORM pg_advisory_xact_lock(chave);
                IF EXISTS (SELECT 1 FROM public.agendamentos a WHERE a.filial_id=NEW.filial_id
                    AND a.barbeiro_id=NEW.barbeiro_id AND a.data=NEW.data
                    AND a.status NOT IN ('cancelado','nao_compareceu')
                    AND a.hora_inicio<NEW.hora_fim AND a.hora_fim>NEW.hora_inicio) THEN
                    RAISE EXCEPTION 'Intervalo contém agendamento'
                        USING ERRCODE='23P01', CONSTRAINT='ex_bloqueio_conflito_agendamento';
                END IF;
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER agendamentos_validar_bloqueio
        BEFORE INSERT OR UPDATE OF filial_id, barbeiro_id, data, hora_inicio, hora_fim, status ON public.agendamentos
        FOR EACH ROW EXECUTE FUNCTION public.validar_ocupacao_agenda()""")
    op.execute("""CREATE TRIGGER bloqueios_validar_agendamento BEFORE INSERT ON public.bloqueios_agenda
        FOR EACH ROW EXECUTE FUNCTION public.validar_ocupacao_agenda()""")


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM public.bloqueios_agenda) THEN
        RAISE EXCEPTION 'Downgrade removeria a auditoria de bloqueios'; END IF; END $$""")
    op.execute('DROP TRIGGER agendamentos_validar_bloqueio ON public.agendamentos')
    op.drop_table('bloqueios_agenda', schema='public')
    op.execute('DROP FUNCTION public.validar_ocupacao_agenda()')
    op.drop_constraint(CHECK_JANELA, 'filiais', schema='public')
    for nome in LIMITES:
        op.drop_constraint(f'ck_filiais_{nome}', 'filiais', schema='public')
        op.drop_column('filiais', nome, schema='public')
