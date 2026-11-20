"""Metadados da vitrine e fila de exclusão de fotos."""
import sqlalchemy as sa
from alembic import op

revision = 'a31d7f05e692'
down_revision = 'f042bd98a561'


def upgrade():
    op.add_column('produtos_estoque', sa.Column('descricao_vitrine', sa.String(1000)), schema='public')
    op.add_column('produtos_estoque', sa.Column('foto_vitrine', sa.String(37)), schema='public')
    op.add_column('produtos_estoque', sa.Column('visivel_vitrine', sa.Boolean(), nullable=False,
        server_default=sa.false()), schema='public')
    op.create_check_constraint('ck_produto_vitrine_revenda', 'produtos_estoque',
        'NOT visivel_vitrine OR (venda AND NOT consumo)', schema='public')
    op.create_check_constraint('ck_produto_vitrine_foto', 'produtos_estoque',
        "foto_vitrine ~ '^[0-9a-f]{32}[.]webp$'", schema='public')
    op.create_table('vitrine_fotos_pendentes',
        sa.Column('caminho', sa.String(37), primary_key=True),
        sa.Column('remover_apos', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("caminho ~ '^[0-9a-f]{32}[.]webp$'", name='ck_vitrine_pendente_caminho'),
        schema='public')
    op.create_index('ix_vitrine_fotos_pendentes_apos', 'vitrine_fotos_pendentes', ['remover_apos'], schema='public')
    op.execute('REVOKE ALL ON public.vitrine_fotos_pendentes FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
    op.execute('GRANT SELECT, INSERT, DELETE ON public.vitrine_fotos_pendentes TO relaxabarber_runtime')
    op.execute('GRANT UPDATE (remover_apos) ON public.vitrine_fotos_pendentes TO relaxabarber_runtime')
    op.execute('GRANT UPDATE (descricao_vitrine, foto_vitrine, visivel_vitrine) ON public.produtos_estoque TO relaxabarber_runtime')


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.vitrine_fotos_pendentes) OR EXISTS (
            SELECT 1 FROM public.produtos_estoque WHERE foto_vitrine IS NOT NULL
                OR descricao_vitrine IS NOT NULL OR visivel_vitrine
        ) THEN RAISE EXCEPTION 'Existem dados ou arquivos da vitrine'; END IF;
        END $$""")
    op.drop_table('vitrine_fotos_pendentes', schema='public')
    for nome in ('ck_produto_vitrine_foto', 'ck_produto_vitrine_revenda'):
        op.drop_constraint(nome, 'produtos_estoque', schema='public', type_='check')
    for nome in ('visivel_vitrine', 'foto_vitrine', 'descricao_vitrine'):
        op.drop_column('produtos_estoque', nome, schema='public')
