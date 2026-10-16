import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, ForeignKeyConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Comanda(Base):
    __tablename__ = "comandas"
    __table_args__ = (
        ForeignKeyConstraint(
            ["agendamento_id", "filial_id", "cliente_id", "barbeiro_id"],
            ["agendamentos.id", "agendamentos.filial_id", "agendamentos.cliente_id", "agendamentos.barbeiro_id"],
            name="fk_comandas_contexto_agendamento",
        ),
        Index("ix_comandas_filial_status", "filial_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), ForeignKey("filiais.id", name="fk_comandas_filial"), nullable=False)
    filial = relationship("Filial")
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey("agendamentos.id"), unique=True, nullable=False)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    data_abertura = Column(DateTime(timezone=True), nullable=True)
    data_fechamento = Column(DateTime(timezone=True), nullable=True)
    valor_total = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(String, nullable=False, default="pendente")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    itens = relationship("ItemComanda", back_populates="comanda", cascade="all, delete-orphan")

class ItemComanda(Base):
    __tablename__ = "itens_comanda"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comanda_id = Column(UUID(as_uuid=True), ForeignKey("comandas.id"), nullable=False)
    tipo = Column(String, nullable=False)  # "servico" ou "produto"
    servico_id = Column(UUID(as_uuid=True), ForeignKey("servicos.id"), nullable=True)
    descricao = Column(String, nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    preco_unitario = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    comanda = relationship("Comanda", back_populates="itens")