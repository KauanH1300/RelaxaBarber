import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, SmallInteger, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Empresa(Base):
    """Identidade única da RelaxaBarber; não representa um tenant."""
    __tablename__ = "empresas"
    __table_args__ = (
        CheckConstraint("singleton = 1", name="ck_empresas_singleton"),
        UniqueConstraint("singleton", name="uq_empresas_singleton"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    singleton: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    data_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    filiais = relationship("Filial", back_populates="empresa", passive_deletes="all")
