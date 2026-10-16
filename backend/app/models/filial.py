import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Filial(Base):
    __tablename__ = "filiais"
    __table_args__ = (
        CheckConstraint("fuso_horario = 'America/Recife'", name="ck_filiais_fuso_horario"),
        Index("ix_filiais_empresa_id", "empresa_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", name="fk_filiais_empresa"), nullable=False)
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    fuso_horario: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'America/Recife'"))
    data_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    empresa = relationship("Empresa", back_populates="filiais")

    clientes = relationship("ClienteFilial", back_populates="filial", passive_deletes="all")
    usuarios = relationship("UsuarioFilial", back_populates="filial", passive_deletes="all")
