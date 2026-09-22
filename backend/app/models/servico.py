import uuid
from sqlalchemy import Column, String, Integer, Numeric, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.db.database import Base


class Servico(Base):
    __tablename__ = "servicos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = Column(String, nullable=False)
    preco = Column(Numeric(10, 2), nullable=False)
    tempo_estimado = Column(Integer, nullable=False)
    comissao_padrao = Column(Numeric(5, 2), nullable=False)
    ativo = Column(Boolean, default=True)
    data_cadastro = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())