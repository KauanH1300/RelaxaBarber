"""Receitas de insumos por serviço e baixa auditada na conclusão."""
import sqlalchemy as sa
from alembic import op

revision = 'f042bd98a561'
down_revision = 'e518fc936b42'


def upgrade():
    op.create_unique_constraint('uq_agendamentos_id_filial', 'agendamentos', ['id', 'filial_id'], schema='public')
    op.create_table('insumos_servico',
        sa.Column('servico_id', sa.Uuid(), sa.ForeignKey('public.servicos.id'), primary_key=True),
        sa.Column('filial_id', sa.Uuid(), primary_key=True),
        sa.Column('produto_id', sa.Uuid(), primary_key=True),
        sa.Column('quantidade', sa.Numeric(14, 3), nullable=False),
        sa.ForeignKeyConstraint(['produto_id', 'filial_id'], ['public.produtos_estoque.id', 'public.produtos_estoque.filial_id']),
        sa.CheckConstraint('quantidade > 0', name='ck_insumo_servico_quantidade'), schema='public')
    op.create_index('ix_insumos_servico_produto', 'insumos_servico', ['produto_id'], schema='public')
    op.create_table('consumos_atendimento',
        sa.Column('agendamento_id', sa.Uuid(), primary_key=True),
        sa.Column('produto_id', sa.Uuid(), primary_key=True),
        sa.Column('filial_id', sa.Uuid(), nullable=False),
        sa.Column('nome', sa.String(150), nullable=False),
        sa.Column('unidade', sa.String(20), nullable=False),
        sa.Column('prevista', sa.Numeric(18, 3), nullable=False),
        sa.Column('baixada', sa.Numeric(14, 3), nullable=False),
        sa.Column('movimento_id', sa.Uuid(), sa.ForeignKey('public.movimentos_estoque.id'), unique=True),
        sa.Column('registrado_por', sa.Uuid(), sa.ForeignKey('public.usuarios.id'), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['produto_id', 'filial_id'], ['public.produtos_estoque.id', 'public.produtos_estoque.filial_id']),
        sa.ForeignKeyConstraint(['agendamento_id', 'filial_id'], ['public.agendamentos.id', 'public.agendamentos.filial_id']),
        sa.CheckConstraint('baixada >= 0 AND prevista > 0 AND baixada <= prevista', name='ck_consumo_quantidades'),
        sa.CheckConstraint('(baixada = 0) = (movimento_id IS NULL)', name='ck_consumo_movimento'), schema='public')
    for tabela, operacoes in [('insumos_servico', 'SELECT, INSERT, DELETE'), ('consumos_atendimento', 'SELECT, INSERT')]:
        op.execute(f'REVOKE ALL ON public.{tabela} FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
        op.execute(f'GRANT {operacoes} ON public.{tabela} TO relaxabarber_runtime')


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.consumos_atendimento) OR EXISTS (SELECT 1 FROM public.insumos_servico) THEN
            RAISE EXCEPTION 'Downgrade removeria configuração ou auditoria de consumo';
        END IF;
    END $$""")
    op.drop_table('consumos_atendimento', schema='public')
    op.drop_table('insumos_servico', schema='public')
    op.drop_constraint('uq_agendamentos_id_filial', 'agendamentos', schema='public', type_='unique')
