import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import time

from app.db.database import Base


class FilialHorario(Base):
    __tablename__ = 'filial_horarios'
    __table_args__ = (
        UniqueConstraint('filial_id', 'dia_semana', name='uq_filial_horarios_dia'),
        CheckConstraint('dia_semana BETWEEN 0 AND 6', name='ck_filial_horarios_dia'),
        CheckConstraint(
            '(fechado AND hora_inicio IS NULL AND hora_fim IS NULL) OR '
            '(NOT fechado AND hora_inicio IS NOT NULL AND hora_fim IS NOT NULL AND hora_inicio < hora_fim)',
            name='ck_filial_horarios_intervalo',
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('filiais.id', name='fk_filial_horarios_filial'), nullable=False)
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    fechado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hora_inicio: Mapped[time | None] = mapped_column(Time(timezone=False), nullable=True)
    hora_fim: Mapped[time | None] = mapped_column(Time(timezone=False), nullable=True)
