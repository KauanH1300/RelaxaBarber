from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Uuid

from app.db.database import Base


class SessaoEquipe(Base):
    __tablename__ = 'equipe_sessoes'
    __table_args__ = (
        Index('ix_equipe_sessoes_usuario', 'usuario_id'),
        Index('ix_equipe_sessoes_expira', 'expira_em'),
    )

    jti_hash = Column(String(64), primary_key=True)
    usuario_id = Column(Uuid, ForeignKey('usuarios.id', ondelete='CASCADE'), nullable=False)
    expira_em = Column(DateTime(timezone=True), nullable=False)
    revogada_em = Column(DateTime(timezone=True))


class RecuperacaoEquipe(Base):
    __tablename__ = 'equipe_recuperacoes'
    __table_args__ = (
        CheckConstraint('tentativas BETWEEN 0 AND 5', name='ck_equipe_recuperacao_tentativas'),
        Index('ix_equipe_recuperacoes_usuario', 'usuario_id'),
        Index('ix_equipe_recuperacoes_expira', 'expira_em'),
    )

    id = Column(Uuid, primary_key=True)
    usuario_id = Column(Uuid, ForeignKey('usuarios.id', ondelete='CASCADE'), nullable=False)
    finalidade = Column(String(20), nullable=False, server_default='recuperacao')
    codigo_hash = Column(String(64), nullable=False)
    credencial_hash = Column(String(64), nullable=False)
    expira_em = Column(DateTime(timezone=True), nullable=False)
    consumida_em = Column(DateTime(timezone=True))
    tentativas = Column(Integer, nullable=False, default=0)
