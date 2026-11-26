"""Categorias do catálogo de serviços."""
from alembic import op
import sqlalchemy as sa

revision = 'a62f18ec304b'
down_revision = '7d8e3c42fa91'
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        'categorias_servicos',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('nome', sa.String(80), nullable=False),
        sa.Column('nome_normalizado', sa.String(), nullable=False, unique=True),
        schema='public',
    )
    op.create_table(
        'servicos_categorias',
        sa.Column('servico_id', sa.Uuid(), sa.ForeignKey('public.servicos.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('categoria_id', sa.Uuid(), sa.ForeignKey('public.categorias_servicos.id'), primary_key=True),
        schema='public',
    )
    for tabela, acoes in (
        ('categorias_servicos', ('SELECT', 'INSERT')),
        ('servicos_categorias', ('SELECT', 'INSERT', 'DELETE')),
    ):
        nome = f'public.{tabela}'
        op.execute(f'ALTER TABLE {nome} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {nome} FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
        op.execute(f'GRANT {", ".join(acoes)} ON {nome} TO relaxabarber_runtime')
        for acao in acoes:
            clausula = 'WITH CHECK (true)' if acao == 'INSERT' else 'USING (true)'
            op.execute(f'CREATE POLICY {tabela}_{acao.lower()} ON {nome} FOR {acao} TO relaxabarber_runtime {clausula}')


def downgrade():
    op.drop_table('servicos_categorias', schema='public')
    op.drop_table('categorias_servicos', schema='public')
