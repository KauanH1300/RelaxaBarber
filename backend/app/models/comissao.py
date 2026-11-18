import uuid
import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base

class ExcecaoComissao(Base):
    __tablename__ = 'excecoes_comissao'
    __table_args__ = (
        ForeignKeyConstraint(['profissional_id','filial_id'], ['usuario_filiais.usuario_id','usuario_filiais.filial_id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['produto_id','filial_id'], ['produtos_estoque.id','produtos_estoque.filial_id'], ondelete='RESTRICT'),
        UniqueConstraint('filial_id','profissional_id','servico_id', name='uq_comissao_excecao_servico'),
        UniqueConstraint('filial_id','profissional_id','produto_id', name='uq_comissao_excecao_produto'),
        CheckConstraint('(servico_id IS NULL) <> (produto_id IS NULL)', name='ck_comissao_excecao_item'),
        CheckConstraint('percentual >= 0 AND percentual <= 100', name='ck_comissao_excecao_percentual'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    profissional_id = Column(UUID(as_uuid=True), nullable=False)
    servico_id = Column(UUID(as_uuid=True), ForeignKey('servicos.id', ondelete='RESTRICT'))
    produto_id = Column(UUID(as_uuid=True))
    percentual = Column(Numeric(5,2), nullable=False)
    ativo = Column(Boolean, nullable=False, default=True, server_default='true')
    atualizado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

class ComissaoItem(Base):
    __tablename__ = 'comissoes_item'
    __table_args__ = (
        ForeignKeyConstraint(['comanda_id','filial_id'], ['comandas.id','comandas.filial_id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['item_id','comanda_id'], ['itens_comanda.id','itens_comanda.comanda_id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['profissional_id','filial_id'], ['usuario_filiais.usuario_id','usuario_filiais.filial_id'], ondelete='RESTRICT'),
        CheckConstraint('percentual >= 0 AND percentual <= 100', name='ck_comissao_item_percentual'),
        CheckConstraint("origem IN ('padrao','excecao')", name='ck_comissao_item_origem'),
    )
    item_id = Column(UUID(as_uuid=True), primary_key=True)
    comanda_id = Column(UUID(as_uuid=True), nullable=False)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    profissional_id = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    servico_id = Column(UUID(as_uuid=True), ForeignKey('servicos.id', ondelete='RESTRICT'), nullable=False)
    percentual = Column(Numeric(5,2), nullable=False)
    origem = Column(sa.String(12), nullable=False)

class EventoComissao(Base):
    __tablename__ = 'eventos_comissao'
    __table_args__ = (
        ForeignKeyConstraint(['comanda_id','filial_id'], ['comandas.id','comandas.filial_id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['item_id','comanda_id'], ['itens_comanda.id','itens_comanda.comanda_id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['profissional_id','filial_id'], ['usuario_filiais.usuario_id','usuario_filiais.filial_id'], ondelete='RESTRICT'),
        CheckConstraint('percentual >= 0 AND percentual <= 100 AND base >= 0 AND gerada >= 0 AND liberada >= 0 AND liberada <= gerada AND paga >= 0', name='ck_evento_comissao_valores'),
        CheckConstraint("origem_percentual IN ('padrao','excecao')", name='ck_evento_comissao_origem'),
        UniqueConstraint('item_id','operacao','chave_operacao', name='uq_evento_comissao_operacao'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ordem = Column(sa.BigInteger, sa.Identity(), nullable=False, unique=True)
    item_id = Column(UUID(as_uuid=True), nullable=False)
    comanda_id = Column(UUID(as_uuid=True), nullable=False)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    profissional_id = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    servico_id = Column(UUID(as_uuid=True), ForeignKey('servicos.id', ondelete='RESTRICT'), nullable=False)
    percentual = Column(Numeric(5,2), nullable=False)
    origem_percentual = Column(sa.String(12), nullable=False)
    base = Column(Numeric(12,2), nullable=False)
    gerada = Column(Numeric(12,2), nullable=False)
    liberada = Column(Numeric(12,2), nullable=False)
    paga = Column(Numeric(12,2), nullable=False, default=0, server_default='0')
    operacao = Column(sa.String(30), nullable=False)
    chave_operacao = Column(UUID(as_uuid=True))
    registrado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'))
    registrado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
