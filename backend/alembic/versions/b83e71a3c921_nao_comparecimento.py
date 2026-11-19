"""Registra não comparecimento explícito na agenda."""
from alembic import op
import sqlalchemy as sa

revision = 'b83e71a3c921'
down_revision = 'a21d4e7b8c90'


def _exclusao(predicado):
    op.execute(f"""ALTER TABLE public.agendamentos ADD CONSTRAINT ex_agendamentos_profissional_periodo
        EXCLUDE USING gist (barbeiro_id WITH =, tsrange(data + hora_inicio, data + hora_fim, '[)') WITH &&)
        WHERE ({predicado}) NOT DEFERRABLE""")


def upgrade():
    op.add_column('agendamentos', sa.Column('falta_registrada_em', sa.DateTime(timezone=True)))
    op.add_column('agendamentos', sa.Column('falta_registrada_por', sa.Uuid()))
    op.add_column('agendamentos', sa.Column('falta_motivo', sa.Text()))
    op.create_foreign_key('fk_agendamento_falta_autor', 'agendamentos', 'usuarios',
                          ['falta_registrada_por'], ['id'], ondelete='RESTRICT')
    op.create_check_constraint('ck_agendamento_auditoria_falta', 'agendamentos', """
        (status = 'nao_compareceu' AND falta_registrada_em IS NOT NULL
         AND falta_registrada_por IS NOT NULL AND falta_motivo IS NOT NULL
         AND length(btrim(falta_motivo)) BETWEEN 1 AND 1000)
        OR (status <> 'nao_compareceu' AND falta_registrada_em IS NULL
         AND falta_registrada_por IS NULL AND falta_motivo IS NULL)
    """)
    op.drop_constraint('ex_agendamentos_profissional_periodo', 'agendamentos')
    _exclusao("status NOT IN ('cancelado', 'nao_compareceu')")
    op.execute("""GRANT UPDATE (falta_registrada_em, falta_registrada_por, falta_motivo)
                  ON public.agendamentos TO relaxabarber_runtime""")


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.agendamentos WHERE status='nao_compareceu') THEN
            RAISE EXCEPTION 'Downgrade apagaria auditoria de não comparecimento';
        END IF;
    END $$""")
    op.drop_constraint('ex_agendamentos_profissional_periodo', 'agendamentos')
    _exclusao("status <> 'cancelado'")
    op.drop_constraint('ck_agendamento_auditoria_falta', 'agendamentos')
    op.drop_constraint('fk_agendamento_falta_autor', 'agendamentos')
    for coluna in ('falta_motivo', 'falta_registrada_por', 'falta_registrada_em'):
        op.drop_column('agendamentos', coluna)

