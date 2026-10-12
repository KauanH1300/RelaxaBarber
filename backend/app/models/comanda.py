import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.database import Base


class Comanda(Base):
    __tablename__ = "comandas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey("agendamentos.id"), unique=True, nullable=False)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    data_abertura = Column(DateTime(timezone=True), nullable=True)
    data_fechamento = Column(DateTime(timezone=True), nullable=True)
    valor_total = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(String, nullable=False, default="pendente")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())