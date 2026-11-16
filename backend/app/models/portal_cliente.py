"""Estado privado do portal; o cadastro e a senha continuam em Cliente."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, JSON, CheckConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base


class ContaPortalCliente(Base):
    __tablename__ = 'portal_clientes_contas'
    cliente_id = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), primary_key=True)
    email_confirmado = Column(String(255), unique=True, nullable=False)
    verificado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    versao = Column(Integer, nullable=False, default=1)
    __table_args__ = (CheckConstraint('versao > 0', name='ck_portal_conta_versao'),)


class DesafioPortalCliente(Base):
    __tablename__ = 'portal_clientes_desafios'
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    finalidade = Column(String(20), nullable=False)
    codigo_hash = Column(String(64), nullable=False)
    email = Column(String(255), nullable=False)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=True)
    dados = Column(JSON, nullable=True)
    expira_em = Column(DateTime(timezone=True), nullable=False)
    tentativas = Column(Integer, nullable=False, default=0)
    consumido = Column(Boolean, nullable=False, default=False)
    __table_args__ = (
        CheckConstraint("finalidade IN ('cadastro','recuperacao')", name='ck_portal_desafio_finalidade'),
        CheckConstraint('tentativas BETWEEN 0 AND 5', name='ck_portal_desafio_tentativas'),
        Index('ix_portal_desafios_expiracao', 'expira_em'),
    )


class LimitePortalCliente(Base):
    __tablename__ = 'portal_clientes_limites'
    chave = Column(String(64), primary_key=True)
    inicio = Column(DateTime(timezone=True), nullable=False)
    ultimo = Column(DateTime(timezone=True), nullable=False)
    quantidade = Column(Integer, nullable=False)


class SessaoPortalCliente(Base):
    __tablename__ = 'portal_clientes_sessoes'
    token_hash = Column(String(64), primary_key=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False, index=True)
    versao = Column(Integer, nullable=False)
    expira_em = Column(DateTime(timezone=True), nullable=False, index=True)
