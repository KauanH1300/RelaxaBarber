"""Confirmação de e-mail e trilha da recuperação administrativa."""

import sqlalchemy as sa
from alembic import op

revision = '3bf126fd81a0'
down_revision = 'a62f18ec304b'


def upgrade():
    op.add_column('usuarios', sa.Column('email_confirmado_em', sa.DateTime(timezone=True)), schema='public')
    op.add_column('equipe_recuperacoes', sa.Column('finalidade', sa.String(20), nullable=False,
                                                  server_default='recuperacao'), schema='public')
    op.create_table(
        'equipe_recuperacoes_auditoria',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('ator_id', sa.Uuid(), nullable=False),
        sa.Column('usuario_id', sa.Uuid(), nullable=False),
        sa.Column('motivo', sa.String(250), nullable=False),
        sa.Column('criada_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema='public',
    )
    op.execute('ALTER TABLE public.equipe_recuperacoes_auditoria ENABLE ROW LEVEL SECURITY')
    op.execute('REVOKE ALL ON public.equipe_recuperacoes_auditoria FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
    op.execute('CREATE POLICY equipe_recuperacoes_auditoria_insert ON public.equipe_recuperacoes_auditoria '
               'FOR INSERT TO relaxabarber_runtime WITH CHECK (true)')
    op.execute('GRANT INSERT ON public.equipe_recuperacoes_auditoria TO relaxabarber_runtime')
    op.execute('GRANT SELECT (email_confirmado_em), UPDATE (email_confirmado_em) ON public.usuarios TO relaxabarber_runtime')


def downgrade():
    op.execute('REVOKE SELECT (email_confirmado_em), UPDATE (email_confirmado_em) ON public.usuarios FROM relaxabarber_runtime')
    op.drop_table('equipe_recuperacoes_auditoria', schema='public')
    op.execute("DELETE FROM public.equipe_recuperacoes WHERE finalidade = 'confirmacao'")
    op.drop_column('equipe_recuperacoes', 'finalidade', schema='public')
    op.drop_column('usuarios', 'email_confirmado_em', schema='public')
