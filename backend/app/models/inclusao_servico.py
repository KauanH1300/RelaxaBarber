"""Auditoria imutável e resultado idempotente da inclusão de serviços."""
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, ForeignKeyConstraint, String, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.database import Base
from app.models.financeiro import ValorFinanceiro


class InclusaoServicoComanda(Base):
    __tablename__ = 'inclusoes_servicos_comanda'
    __table_args__ = (
        ForeignKeyConstraint(['comanda_id', 'filial_id'], ['comandas.id', 'comandas.filial_id'], name='fk_inclusao_contexto', ondelete='RESTRICT'),
        UniqueConstraint('comanda_id', 'chave_idempotencia', name='uq_inclusao_idempotencia'),
        UniqueConstraint('item_id', name='uq_inclusao_item'),
        CheckConstraint('length(fingerprint) = 64', name='ck_inclusao_fingerprint'),
        CheckConstraint('total_resultante >= 0 AND total_resultante <= 99999999.99', name='ck_inclusao_total'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comanda_id = Column(UUID(as_uuid=True), nullable=False)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey('itens_comanda.id', ondelete='RESTRICT'), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    total_resultante = Column(ValorFinanceiro(), nullable=False)
