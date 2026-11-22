from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID

from app.db.database import Base


class ParCliente(Base):
    __tablename__ = 'clientes_pares'
    __table_args__ = (
        CheckConstraint('cliente_a < cliente_b', name='ck_clientes_par_ordem'),
        CheckConstraint("estado IN ('encaminhado','diferentes','associado','reaberto')", name='ck_clientes_par_estado'),
        CheckConstraint("""(estado = 'associado' AND principal_id IS NOT NULL AND associado_id IS NOT NULL
            AND ((principal_id = cliente_a AND associado_id = cliente_b) OR
                 (principal_id = cliente_b AND associado_id = cliente_a))) OR
            (estado <> 'associado' AND principal_id IS NULL AND associado_id IS NULL)""",
                        name='ck_clientes_par_associacao'),
        Index('uq_clientes_par_associado', 'associado_id', unique=True),
        Index('ix_clientes_par_principal', 'principal_id'),
    )

    cliente_a = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), primary_key=True)
    cliente_b = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), primary_key=True)
    filial_id = Column(UUID(as_uuid=True), ForeignKey('filiais.id', ondelete='RESTRICT'), nullable=False)
    estado = Column(String(20), nullable=False)
    principal_id = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'))
    associado_id = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'))
    versao = Column(UUID(as_uuid=True), nullable=False)


class DecisaoCliente(Base):
    __tablename__ = 'clientes_decisoes'
    chave = Column(UUID(as_uuid=True), primary_key=True)
    cliente_a = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False)
    cliente_b = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), nullable=False)
    filial_id = Column(UUID(as_uuid=True), ForeignKey('filiais.id', ondelete='RESTRICT'), nullable=False)
    ator_id = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    acao = Column(String(20), nullable=False)
    estado_anterior = Column(String(20), nullable=False)
    estado = Column(String(20), nullable=False)
    principal_id = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'))
    metodo = Column(String(40))
    justificativa = Column(String(500), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
