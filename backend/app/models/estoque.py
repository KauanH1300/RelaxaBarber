import uuid
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base

class CategoriaEstoque(Base):
    __tablename__ = 'categorias_estoque'
    __table_args__ = (UniqueConstraint('id', 'filial_id', name='uq_categoria_estoque_filial'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), ForeignKey('filiais.id'), nullable=False)
    nome = Column(String(100), nullable=False)

class MarcaEstoque(Base):
    __tablename__ = 'marcas_estoque'
    __table_args__ = (UniqueConstraint('id', 'filial_id', name='uq_marca_estoque_filial'),)
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), ForeignKey('filiais.id'), nullable=False)
    nome = Column(String(100), nullable=False)

class ProdutoEstoque(Base):
    __tablename__ = 'produtos_estoque'
    __table_args__ = (UniqueConstraint('id', 'filial_id', name='uq_produto_estoque_filial'),
        ForeignKeyConstraint(['categoria_id', 'filial_id'], ['categorias_estoque.id', 'categorias_estoque.filial_id'], name='fk_produto_categoria_filial'),
        ForeignKeyConstraint(['marca_id', 'filial_id'], ['marcas_estoque.id', 'marcas_estoque.filial_id'], name='fk_produto_marca_filial'),
        CheckConstraint("venda OR consumo", name='ck_produto_finalidade'),
        CheckConstraint("comissao_padrao >= 0 AND comissao_padrao <= 100", name='ck_produto_comissao'),
        CheckConstraint("length(trim(nome)) > 0 AND length(trim(unidade)) > 0", name='ck_produto_nome_unidade'),
        CheckConstraint("custo >= 0 AND estoque_minimo >= 0 AND saldo >= 0 AND (preco_venda IS NULL OR preco_venda >= 0) AND (NOT venda OR preco_venda IS NOT NULL)", name='ck_produto_valores'))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), ForeignKey('filiais.id'), nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    categoria_id = Column(UUID(as_uuid=True))
    marca_id = Column(UUID(as_uuid=True))
    unidade = Column(String(20), nullable=False)
    venda = Column(Boolean, nullable=False)
    consumo = Column(Boolean, nullable=False)
    custo = Column(Numeric(12,2), nullable=False)
    preco_venda = Column(Numeric(12,2))
    comissao_padrao = Column(Numeric(5,2), nullable=False, default=0, server_default='0')
    estoque_minimo = Column(Numeric(14,3), nullable=False)
    saldo = Column(Numeric(14,3), nullable=False, server_default='0')
    ativo = Column(Boolean, nullable=False, server_default='true')
    descricao_vitrine = Column(String(1000))
    foto_vitrine = Column(String(37))
    visivel_vitrine = Column(Boolean, nullable=False, server_default='false')

class MovimentoEstoque(Base):
    __tablename__ = 'movimentos_estoque'
    __table_args__ = (ForeignKeyConstraint(['produto_id','filial_id'], ['produtos_estoque.id','produtos_estoque.filial_id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['comanda_id','filial_id'], ['comandas.id','comandas.filial_id'], name='fk_movimento_comanda_filial'),
        ForeignKeyConstraint(['item_comanda_id','comanda_id'], ['itens_comanda.id','itens_comanda.comanda_id'], name='fk_movimento_item_comanda'),
        ForeignKeyConstraint(['item_comanda_id','comanda_id','produto_id','filial_id'], ['itens_comanda.id','itens_comanda.comanda_id','itens_comanda.produto_id','itens_comanda.filial_id'], name='fk_movimento_item_produto_filial'),
        UniqueConstraint('comanda_id','chave_idempotencia', name='uq_movimento_comanda_chave'),
        CheckConstraint('(comanda_id IS NULL) = (item_comanda_id IS NULL)', name='ck_movimento_contexto_comanda'),
        UniqueConstraint('produto_id','chave_idempotencia', name='uq_movimento_estoque_chave'),
        CheckConstraint("tipo IN ('entrada','baixa','ajuste') AND quantidade <> 0 AND saldo_apos >= 0 AND length(trim(motivo)) > 0", name='ck_movimento_estoque'))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    produto_id = Column(UUID(as_uuid=True), nullable=False)
    comanda_id = Column(UUID(as_uuid=True), nullable=True)
    item_comanda_id = Column(UUID(as_uuid=True), nullable=True)
    filial_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tipo = Column(String(12), nullable=False)
    quantidade = Column(Numeric(14,3), nullable=False)
    saldo_apos = Column(Numeric(14,3), nullable=False)
    motivo = Column(Text, nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id'), nullable=False)
    registrado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
