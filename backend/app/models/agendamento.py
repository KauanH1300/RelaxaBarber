import uuid
from sqlalchemy import Column, String, Date, Time, Text, Integer, Numeric, ForeignKey, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base


class Agendamento(Base):
    __tablename__ = "agendamentos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False)
    data = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fim = Column(Time, nullable=False)
    status = Column(String(20), nullable=False, default="pendente")
    origem = Column(String(20), nullable=False)
    observacoes = Column(Text, nullable=True)
    criado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    data_cadastro = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    servicos = relationship("AgendamentoServico", back_populates="agendamento", cascade="all, delete-orphan")
    cliente = relationship("Cliente")
    barbeiro = relationship("Usuario", foreign_keys=[barbeiro_id])

class AgendamentoServico(Base):
    __tablename__ = "agendamento_servicos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey("agendamentos.id"), nullable=False)
    servico_id = Column(UUID(as_uuid=True), ForeignKey("servicos.id"), nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)
    tempo_estimado = Column(Integer, nullable=False)  # minutos

    agendamento = relationship("Agendamento", back_populates="servicos")
    servico = relationship("Servico")