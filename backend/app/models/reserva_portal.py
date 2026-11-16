from sqlalchemy import Column, String, ForeignKey, ForeignKeyConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.database import Base


class HabilitacaoServico(Base):
    __tablename__ = 'habilitacoes_servicos'
    filial_id = Column(UUID(as_uuid=True), primary_key=True)
    barbeiro_id = Column(UUID(as_uuid=True), primary_key=True)
    servico_id = Column(UUID(as_uuid=True), ForeignKey('servicos.id', ondelete='RESTRICT'), primary_key=True)
    __table_args__ = (ForeignKeyConstraint(['barbeiro_id','filial_id'],
        ['usuario_filiais.usuario_id','usuario_filiais.filial_id'], ondelete='RESTRICT'),)


class RestricaoServico(Base):
    __tablename__ = 'restricoes_servicos'
    filial_id = Column(UUID(as_uuid=True), primary_key=True)
    barbeiro_id = Column(UUID(as_uuid=True), primary_key=True)
    servico_id = Column(UUID(as_uuid=True), ForeignKey('servicos.id', ondelete='RESTRICT'), primary_key=True)
    __table_args__ = (ForeignKeyConstraint(['barbeiro_id','filial_id'],
        ['usuario_filiais.usuario_id','usuario_filiais.filial_id'], ondelete='RESTRICT'),)


class ReservaPortal(Base):
    __tablename__ = 'portal_clientes_reservas'
    cliente_id = Column(UUID(as_uuid=True), ForeignKey('clientes.id', ondelete='RESTRICT'), primary_key=True)
    chave = Column(UUID(as_uuid=True), primary_key=True)
    fingerprint = Column(String(64), nullable=False)
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey('agendamentos.id', ondelete='RESTRICT'), nullable=False, unique=True)
