"""Cadastro e movimentação manual de estoque por filial."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
revision = 'e70c15a9f321'
down_revision = 'd17a60c28e94'
branch_labels = depends_on = None

def upgrade():
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='relaxabarber_runtime'
                       AND NOT rolsuper AND NOT rolbypassrls) THEN
            RAISE EXCEPTION 'relaxabarber_runtime ausente ou privilegiado';
        END IF;
    END $$""")
    op.create_table('produtos_estoque',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('filial_id', pg.UUID(as_uuid=True), sa.ForeignKey('public.filiais.id'), nullable=False),
        sa.Column('nome', sa.String(150), nullable=False), sa.Column('unidade', sa.String(20), nullable=False),
        sa.Column('venda', sa.Boolean(), nullable=False), sa.Column('consumo', sa.Boolean(), nullable=False),
        sa.Column('custo', sa.Numeric(12,2), nullable=False), sa.Column('preco_venda', sa.Numeric(12,2)),
        sa.Column('estoque_minimo', sa.Numeric(14,3), nullable=False), sa.Column('saldo', sa.Numeric(14,3), nullable=False, server_default='0'),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint('id','filial_id', name='uq_produto_estoque_filial'),
        sa.CheckConstraint('venda OR consumo', name='ck_produto_finalidade'),
        sa.CheckConstraint('length(trim(nome)) > 0 AND length(trim(unidade)) > 0', name='ck_produto_nome_unidade'),
        sa.CheckConstraint('custo >= 0 AND estoque_minimo >= 0 AND saldo >= 0 AND (preco_venda IS NULL OR preco_venda >= 0) AND (NOT venda OR preco_venda IS NOT NULL)', name='ck_produto_valores'), schema='public')
    op.create_index('ix_produtos_estoque_filial_id', 'produtos_estoque', ['filial_id'], schema='public')
    op.create_table('movimentos_estoque',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True), sa.Column('produto_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('filial_id', pg.UUID(as_uuid=True), nullable=False), sa.Column('tipo', sa.String(12), nullable=False),
        sa.Column('quantidade', sa.Numeric(14,3), nullable=False), sa.Column('saldo_apos', sa.Numeric(14,3), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False), sa.Column('registrado_por', pg.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id'), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('chave_idempotencia', pg.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['produto_id','filial_id'], ['public.produtos_estoque.id','public.produtos_estoque.filial_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('produto_id','chave_idempotencia', name='uq_movimento_estoque_chave'),
        sa.CheckConstraint("tipo IN ('entrada','baixa','ajuste') AND quantidade <> 0 AND saldo_apos >= 0 AND length(trim(motivo)) > 0", name='ck_movimento_estoque'), schema='public')
    op.create_index('ix_movimentos_estoque_filial_id', 'movimentos_estoque', ['filial_id'], schema='public')
    spec = spec_from_file_location('financeiro_acl_estoque', Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    modulo = module_from_spec(spec); spec.loader.exec_module(modulo)
    for tabela in ('produtos_estoque', 'movimentos_estoque'):
        modulo.proteger_tabela(tabela)
    op.execute('GRANT UPDATE (nome, unidade, venda, consumo, custo, preco_venda, estoque_minimo, saldo, ativo) ON public.produtos_estoque TO relaxabarber_runtime')
    op.execute('CREATE POLICY estoque_runtime_update ON public.produtos_estoque FOR UPDATE TO relaxabarber_runtime USING (true) WITH CHECK (true)')
    op.execute('CREATE TRIGGER movimentos_estoque_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.movimentos_estoque FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()')
    op.execute('''CREATE FUNCTION public.estoque_carimbar() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN NEW.registrado_em := clock_timestamp(); RETURN NEW; END $$''')
    op.execute('REVOKE ALL ON FUNCTION public.estoque_carimbar() FROM PUBLIC')
    op.execute('CREATE TRIGGER movimentos_estoque_carimbo BEFORE INSERT ON public.movimentos_estoque FOR EACH ROW EXECUTE FUNCTION public.estoque_carimbar()')

def downgrade():
    raise NotImplementedError('Preservar o histórico de estoque exige plano de reversão próprio')
