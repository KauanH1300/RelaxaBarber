import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from decimal import Decimal

from app.db.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    telefone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=True, index=True)
    # Opcional: só existe depois que o cliente "ativa" a conta e define  uma senha (via e-mail). Enquanto for null, o cliente
    # não consegue fazer login — só existe no sistema como cadastro.
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    conta_ativada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    saldo: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_cadastro: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Cliente id={self.id} telefone={self.telefone} email={self.email}>"