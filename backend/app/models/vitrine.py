from sqlalchemy import Column, DateTime, String

from app.db.database import Base


class FotoPendente(Base):
    __tablename__ = 'vitrine_fotos_pendentes'
    caminho = Column(String(37), primary_key=True)
    remover_apos = Column(DateTime(timezone=True), nullable=False)
