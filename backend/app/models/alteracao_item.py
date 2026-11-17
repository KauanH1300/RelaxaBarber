"""Resultados originais imutáveis, independentes do estado atual dos itens."""
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, ForeignKeyConstraint, JSON, String, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.db.database import Base


class RespostaInclusaoComanda(Base):
    __tablename__ = 'respostas_inclusoes_comanda'
    inclusao_id = Column(UUID(as_uuid=True), ForeignKey('inclusoes_servicos_comanda.id', ondelete='RESTRICT'), primary_key=True)
    resposta = Column(JSON().with_variant(JSONB(), 'postgresql'), nullable=False)


class AlteracaoItemComanda(Base):
    __tablename__ = 'alteracoes_itens_comanda'
    __table_args__ = (
        ForeignKeyConstraint(['comanda_id', 'filial_id'], ['comandas.id', 'comandas.filial_id'], ondelete='RESTRICT'),
        UniqueConstraint('comanda_id', 'chave_idempotencia', name='uq_alteracao_item_idempotencia'),
        CheckConstraint('length(fingerprint)=64', name='ck_alteracao_item_fingerprint'),
        CheckConstraint('length(trim(motivo))>0', name='ck_alteracao_item_motivo'),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comanda_id = Column(UUID(as_uuid=True), nullable=False)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey('itens_comanda.id', ondelete='RESTRICT'), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    motivo = Column(Text, nullable=False)
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    resultado = Column(JSON().with_variant(JSONB(), 'postgresql'), nullable=False)
