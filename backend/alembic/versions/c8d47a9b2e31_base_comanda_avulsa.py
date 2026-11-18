"""Base estrutural de comandas avulsas, sem operações de venda."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'c8d47a9b2e31'
down_revision = 'a38f72b96c14'
branch_labels = depends_on = None


def upgrade():
    op.add_column('comandas', sa.Column('tipo', sa.String(12), nullable=False, server_default='agendada'), schema='public')
    op.add_column('comandas', sa.Column('chave_abertura', UUID(as_uuid=True)), schema='public')
    op.add_column('comandas', sa.Column('abertura_por', UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id')), schema='public')
    op.create_unique_constraint('uq_comanda_abertura_filial', 'comandas', ['filial_id', 'chave_abertura'], schema='public')
    op.create_check_constraint('ck_comanda_abertura_avulsa', 'comandas', "(chave_abertura IS NULL AND abertura_por IS NULL) OR (tipo = 'avulsa' AND chave_abertura IS NOT NULL AND abertura_por IS NOT NULL)", schema='public')
    for campo in ('agendamento_id', 'cliente_id', 'barbeiro_id'):
        op.alter_column('comandas', campo, existing_type=UUID(as_uuid=True), nullable=True, schema='public')
    op.create_check_constraint('ck_comanda_tipo_contexto', 'comandas', "(tipo = 'agendada' AND agendamento_id IS NOT NULL AND cliente_id IS NOT NULL AND barbeiro_id IS NOT NULL) OR (tipo = 'avulsa' AND agendamento_id IS NULL)", schema='public')
    op.create_unique_constraint('uq_comanda_id_tipo', 'comandas', ['id', 'tipo'], schema='public')
    for coluna in (
        sa.Column('comanda_tipo', sa.String(12), nullable=False, server_default='agendada'),
        sa.Column('filial_id', UUID(as_uuid=True)),
        sa.Column('produto_id', UUID(as_uuid=True)),
        sa.Column('custo_snapshot', sa.Numeric(12, 2)),
        sa.Column('comissao_percentual_snapshot', sa.Numeric(5, 2)),
        sa.Column('comissao_profissional_id', UUID(as_uuid=True)),
    ):
        op.add_column('itens_comanda', coluna, schema='public')
    op.create_foreign_key('fk_item_comanda_tipo', 'itens_comanda', 'comandas', ['comanda_id', 'comanda_tipo'], ['id', 'tipo'], source_schema='public', referent_schema='public')
    op.create_foreign_key('fk_item_comanda_filial', 'itens_comanda', 'comandas', ['comanda_id', 'filial_id'], ['id', 'filial_id'], source_schema='public', referent_schema='public')
    op.create_foreign_key('fk_item_produto_filial', 'itens_comanda', 'produtos_estoque', ['produto_id', 'filial_id'], ['id', 'filial_id'], source_schema='public', referent_schema='public')
    op.create_foreign_key('fk_item_comissao_profissional_filial', 'itens_comanda', 'usuario_filiais', ['comissao_profissional_id', 'filial_id'], ['usuario_id', 'filial_id'], source_schema='public', referent_schema='public')
    op.create_check_constraint('ck_item_avulso_produto', 'itens_comanda', "comanda_tipo = 'agendada' OR (comanda_tipo = 'avulsa' AND tipo = 'produto' AND servico_id IS NULL AND produto_id IS NOT NULL AND filial_id IS NOT NULL AND quantidade > 0 AND preco_unitario >= 0 AND custo_snapshot IS NOT NULL AND custo_snapshot >= 0 AND comissao_percentual_snapshot IS NOT NULL AND comissao_percentual_snapshot BETWEEN 0 AND 100)", schema='public')
    op.create_unique_constraint('uq_item_comanda_produto_filial', 'itens_comanda', ['id', 'comanda_id', 'produto_id', 'filial_id'], schema='public')
    op.add_column('movimentos_estoque', sa.Column('comanda_id', UUID(as_uuid=True)), schema='public')
    op.add_column('movimentos_estoque', sa.Column('item_comanda_id', UUID(as_uuid=True)), schema='public')
    op.create_foreign_key('fk_movimento_comanda_filial', 'movimentos_estoque', 'comandas', ['comanda_id', 'filial_id'], ['id', 'filial_id'], source_schema='public', referent_schema='public')
    op.create_foreign_key('fk_movimento_item_comanda', 'movimentos_estoque', 'itens_comanda', ['item_comanda_id', 'comanda_id'], ['id', 'comanda_id'], source_schema='public', referent_schema='public')
    op.create_foreign_key('fk_movimento_item_produto_filial', 'movimentos_estoque', 'itens_comanda', ['item_comanda_id', 'comanda_id', 'produto_id', 'filial_id'], ['id', 'comanda_id', 'produto_id', 'filial_id'], source_schema='public', referent_schema='public')
    op.create_unique_constraint('uq_movimento_comanda_chave', 'movimentos_estoque', ['comanda_id', 'chave_idempotencia'], schema='public')
    op.create_check_constraint('ck_movimento_contexto_comanda', 'movimentos_estoque', '(comanda_id IS NULL) = (item_comanda_id IS NULL)', schema='public')
    for tabela, prefixo in (('comissoes_item', 'comissao_item'), ('eventos_comissao', 'evento_comissao')):
        op.alter_column(tabela, 'servico_id', existing_type=UUID(as_uuid=True), nullable=True, schema='public')
        op.add_column(tabela, sa.Column('produto_id', UUID(as_uuid=True)), schema='public')
        op.create_foreign_key(f'fk_{prefixo}_produto_filial', tabela, 'produtos_estoque', ['produto_id', 'filial_id'], ['id', 'filial_id'], source_schema='public', referent_schema='public', ondelete='RESTRICT')
        op.create_check_constraint(f'ck_{prefixo}_origem_tipo', tabela, '(servico_id IS NULL) <> (produto_id IS NULL)', schema='public')


def downgrade():
    raise NotImplementedError('A reversão requer preservar comandas avulsas e seus itens')
