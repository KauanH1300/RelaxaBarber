import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base


class ClienteFilial(Base):
    """Presença operacional; cadastro e atividade do cliente são globais."""
    __tablename__ = "cliente_filiais"
    __table_args__ = (
        UniqueConstraint("cliente_id", "filial_id", name="uq_cliente_filiais_cliente_filial"),
        Index("ix_cliente_filiais_filial_id", "filial_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clientes.id", name="fk_cliente_filiais_cliente"), nullable=False)
    filial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("filiais.id", name="fk_cliente_filiais_filial"), nullable=False)
    data_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    cliente = relationship("Cliente", back_populates="filiais")
    filial = relationship("Filial", back_populates="clientes")
