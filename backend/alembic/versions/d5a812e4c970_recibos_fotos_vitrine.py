"""Recibos imutáveis para conferência de uploads da vitrine."""
import sqlalchemy as sa
from alembic import op

revision = 'd5a812e4c970'
down_revision = 'b64f8d20c371'


def upgrade():
    op.create_table('vitrine_uploads_confirmados',
        sa.Column('filial_id', sa.Uuid(), primary_key=True),
        sa.Column('produto_id', sa.Uuid(), primary_key=True),
        sa.Column('operador_id', sa.Uuid(), primary_key=True),
        sa.Column('chave', sa.Uuid(), primary_key=True),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('caminho', sa.String(37), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['produto_id', 'filial_id'], ['public.produtos_estoque.id', 'public.produtos_estoque.filial_id'],
                                name='fk_vitrine_upload_produto_filial', ondelete='CASCADE'),
        sa.CheckConstraint("caminho ~ '^[0-9a-f]{32}[.]webp$'", name='ck_vitrine_upload_caminho'),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name='ck_vitrine_upload_fingerprint'),
        schema='public')
    op.execute('REVOKE ALL ON public.vitrine_uploads_confirmados FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
    op.execute('GRANT SELECT, INSERT ON public.vitrine_uploads_confirmados TO relaxabarber_runtime')
    op.execute('ALTER TABLE public.vitrine_uploads_confirmados ENABLE ROW LEVEL SECURITY')
    op.execute('CREATE POLICY vitrine_upload_runtime_select ON public.vitrine_uploads_confirmados FOR SELECT TO relaxabarber_runtime USING (true)')
    op.execute('CREATE POLICY vitrine_upload_runtime_insert ON public.vitrine_uploads_confirmados FOR INSERT TO relaxabarber_runtime WITH CHECK (true)')


def downgrade():
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM public.vitrine_uploads_confirmados)
        THEN RAISE EXCEPTION 'Existem recibos de upload da vitrine'; END IF; END $$""")
    op.drop_table('vitrine_uploads_confirmados', schema='public')
