"""Benefícios sem reprecificar itens nem reescrever histórico financeiro."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'ab72d90e613f'
down_revision = 'c61e9a4b207d'
branch_labels = depends_on = None


def upgrade():
    for table in ['comandas', 'itens_comanda']:
        op.add_column(table, sa.Column('desconto_tipo', sa.String(12), nullable=False, server_default='nenhum'), schema='public')
        op.add_column(table, sa.Column('desconto_valor', sa.Numeric(10, 2), nullable=False, server_default='0'), schema='public')
    op.create_check_constraint('ck_comanda_desconto', 'comandas',
        "desconto_tipo IN ('nenhum','valor','percentual') AND desconto_valor >= 0 AND desconto_valor <= 99999999.99 AND (desconto_tipo <> 'percentual' OR desconto_valor <= 100) AND (desconto_tipo <> 'nenhum' OR desconto_valor = 0)", schema='public')
    op.create_check_constraint('ck_item_desconto', 'itens_comanda',
        "desconto_tipo IN ('nenhum','valor','percentual','cortesia') AND desconto_valor >= 0 AND desconto_valor <= 99999999.99 AND (desconto_tipo <> 'percentual' OR desconto_valor <= 100) AND (desconto_tipo NOT IN ('nenhum','cortesia') OR desconto_valor = 0) AND (desconto_tipo <> 'valor' OR desconto_valor <= quantidade * preco_unitario)", schema='public')
    op.create_table('beneficios_comanda',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('comanda_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('filial_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('item_id', pg.UUID(as_uuid=True), sa.ForeignKey('public.itens_comanda.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('registrado_por', pg.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('chave_idempotencia', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('resultado', pg.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['comanda_id', 'filial_id'], ['public.comandas.id', 'public.comandas.filial_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('comanda_id', 'chave_idempotencia', name='uq_beneficio_idempotencia'),
        sa.CheckConstraint('length(fingerprint)=64', name='ck_beneficio_fingerprint'),
        sa.CheckConstraint('length(trim(motivo))>0', name='ck_beneficio_motivo'), schema='public')
    spec = spec_from_file_location('financeiro_acl', Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    modulo = module_from_spec(spec); spec.loader.exec_module(modulo)
    modulo.proteger_tabela('beneficios_comanda')
    op.execute('CREATE TRIGGER beneficios_comanda_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.beneficios_comanda FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()')
    op.execute('CREATE TRIGGER beneficio_carimbo BEFORE INSERT ON public.beneficios_comanda FOR EACH ROW EXECUTE FUNCTION public.itens_carimbar_alteracao()')
    for table in ['comandas', 'itens_comanda']:
        op.execute(f'GRANT UPDATE (desconto_tipo,desconto_valor) ON public.{table} TO relaxabarber_runtime')


def downgrade():
    raise NotImplementedError('Preservar benefícios e fechamentos gratuitos: reversão exige plano próprio')
