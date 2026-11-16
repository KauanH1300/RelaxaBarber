import uuid
from sqlalchemy import ForeignKey, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class JornadaBarbeiro(Base):
    __tablename__ = 'jornadas_barbeiros'
    __table_args__ = (UniqueConstraint('filial_id', 'barbeiro_id', name='uq_jornada_filial_barbeiro'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('filiais.id'), nullable=False)
    barbeiro_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('usuarios.id'), nullable=False)
    configuracao: Mapped[dict] = mapped_column(JSON, nullable=False)
