import uuid
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base

class ProdutoEstoque(Base):
    __tablename__ = 'produtos_estoque'
    __table_args__ = (UniqueConstraint('id', 'filial_id', name='uq_produto_estoque_filial'),
        CheckConstraint("venda OR consumo", name='ck_produto_finalidade'),
        CheckConstraint("length(trim(nome)) > 0 AND length(trim(unidade)) > 0", name='ck_produto_nome_unidade'),
        CheckConstraint("custo >= 0 AND estoque_minimo >= 0 AND saldo >= 0 AND (preco_venda IS NULL OR preco_venda >= 0) AND (NOT venda OR preco_venda IS NOT NULL)", name='ck_produto_valores'))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), ForeignKey('filiais.id'), nullable=False, index=True)
    nome = Column(String(150), nullable=False)
    unidade = Column(String(20), nullable=False)
    venda = Column(Boolean, nullable=False)
    consumo = Column(Boolean, nullable=False)
    custo = Column(Numeric(12,2), nullable=False)
    preco_venda = Column(Numeric(12,2))
    estoque_minimo = Column(Numeric(14,3), nullable=False)
    saldo = Column(Numeric(14,3), nullable=False, server_default='0')
    ativo = Column(Boolean, nullable=False, server_default='true')

class MovimentoEstoque(Base):
    __tablename__ = 'movimentos_estoque'
    __table_args__ = (ForeignKeyConstraint(['produto_id','filial_id'], ['produtos_estoque.id','produtos_estoque.filial_id'], ondelete='RESTRICT'),
        UniqueConstraint('produto_id','chave_idempotencia', name='uq_movimento_estoque_chave'),
        CheckConstraint("tipo IN ('entrada','baixa','ajuste') AND quantidade <> 0 AND saldo_apos >= 0 AND length(trim(motivo)) > 0", name='ck_movimento_estoque'))
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    produto_id = Column(UUID(as_uuid=True), nullable=False)
    filial_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    tipo = Column(String(12), nullable=False)
    quantidade = Column(Numeric(14,3), nullable=False)
    saldo_apos = Column(Numeric(14,3), nullable=False)
    motivo = Column(Text, nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id'), nullable=False)
    registrado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
