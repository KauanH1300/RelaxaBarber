"""Histórico de mudanças da reserva, independente dos registros financeiros."""
import uuid
from sqlalchemy import Column, Date, Time, DateTime, ForeignKey, String, CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base


class Reagendamento(Base):
    __tablename__ = 'reagendamentos'
    __table_args__ = (
        CheckConstraint('(registrado_por IS NOT NULL) <> (registrado_por_cliente IS NOT NULL)', name='ck_reagendamento_autor'),
        CheckConstraint('hora_fim_anterior > hora_inicio_anterior', name='ck_reagendamento_anterior'),
        CheckConstraint('hora_fim_nova > hora_inicio_nova', name='ck_reagendamento_novo'),
        Index('ix_reagendamentos_reserva_registro', 'agendamento_id', 'registrado_em'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey('agendamentos.id', ondelete='RESTRICT'), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=True)
    registrado_por_cliente = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=True)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    motivo = Column(String(1000), nullable=True)
    data_anterior = Column(Date, nullable=False)
    hora_inicio_anterior = Column(Time, nullable=False)
    hora_fim_anterior = Column(Time, nullable=False)
    barbeiro_id_anterior = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    data_nova = Column(Date, nullable=False)
    hora_inicio_nova = Column(Time, nullable=False)
    hora_fim_nova = Column(Time, nullable=False)
    barbeiro_id_novo = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
