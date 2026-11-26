import uuid
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime, CheckConstraint, ForeignKey, Table
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


servicos_categorias = Table(
    "servicos_categorias", Base.metadata,
    Column("servico_id", UUID(as_uuid=True), ForeignKey("servicos.id", ondelete="CASCADE"), primary_key=True),
    Column("categoria_id", UUID(as_uuid=True), ForeignKey("categorias_servicos.id"), primary_key=True),
)


class CategoriaServico(Base):
    __tablename__ = "categorias_servicos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String(80), nullable=False)
    nome_normalizado = Column(String, nullable=False, unique=True)


class Servico(Base):
    __tablename__ = "servicos"
    __table_args__ = (CheckConstraint("comissao_padrao >= 0 AND comissao_padrao <= 100", name="ck_servico_comissao"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String, nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)
    tempo_estimado = Column(Integer, nullable=False)
    comissao_padrao = Column(Numeric(5, 2), nullable=False)
    ativo = Column(Boolean, default=True)
    data_cadastro = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
    categorias = relationship(CategoriaServico, secondary=servicos_categorias, order_by=CategoriaServico.nome)
