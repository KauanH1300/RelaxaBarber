"""Cancelamento direto imutável, independente do cancelamento do agendamento."""
from sqlalchemy import Column, DateTime, ForeignKey, ForeignKeyConstraint, CheckConstraint, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.db.database import Base


class CancelamentoComanda(Base):
    __tablename__ = 'cancelamentos_comanda'
    __table_args__ = (
        ForeignKeyConstraint(['comanda_id', 'filial_id'], ['comandas.id', 'comandas.filial_id'], ondelete='RESTRICT'),
        CheckConstraint('length(trim(motivo))>0', name='ck_cancelamento_comanda_motivo'),
        CheckConstraint('length(fingerprint)=64', name='ck_cancelamento_comanda_fingerprint'),
    )
    comanda_id = Column(UUID(as_uuid=True), primary_key=True)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    motivo = Column(Text, nullable=False)
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    resultado = Column(JSON().with_variant(JSONB(), 'postgresql'), nullable=False)
