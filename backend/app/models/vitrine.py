from sqlalchemy import Column, DateTime, ForeignKeyConstraint, String, Uuid, func

from app.db.database import Base


class FotoPendente(Base):
    __tablename__ = 'vitrine_fotos_pendentes'
    caminho = Column(String(37), primary_key=True)
    remover_apos = Column(DateTime(timezone=True), nullable=False)


class UploadConfirmado(Base):
    __tablename__ = 'vitrine_uploads_confirmados'
    __table_args__ = (ForeignKeyConstraint(['produto_id', 'filial_id'], ['produtos_estoque.id', 'produtos_estoque.filial_id'],
                                           name='fk_vitrine_upload_produto_filial', ondelete='CASCADE'),)
    filial_id = Column(Uuid, primary_key=True)
    produto_id = Column(Uuid, primary_key=True)
    operador_id = Column(Uuid, primary_key=True)
    chave = Column(Uuid, primary_key=True)
    fingerprint = Column(String(64), nullable=False)
    caminho = Column(String(37), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
