import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base


class UsuarioFilial(Base):
    """Vínculo lógico; perfil e atividade global permanecem em Usuario."""
    __tablename__ = "usuario_filiais"
    __table_args__ = (
        UniqueConstraint("usuario_id", "filial_id", name="uq_usuario_filiais_usuario_filial"),
        Index("ix_usuario_filiais_filial_id", "filial_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("usuarios.id", name="fk_usuario_filiais_usuario"), nullable=False)
    filial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("filiais.id", name="fk_usuario_filiais_filial"), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    data_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    usuario = relationship("Usuario", back_populates="filiais")
    filial = relationship("Filial", back_populates="usuarios")
