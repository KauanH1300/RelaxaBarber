import uuid

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Text, Time, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID

from app.db.database import Base


class BloqueioAgenda(Base):
    __tablename__ = 'bloqueios_agenda'
    __table_args__ = (
        CheckConstraint('hora_inicio < hora_fim', name='ck_bloqueio_intervalo'),
        CheckConstraint('length(trim(motivo)) BETWEEN 1 AND 1000', name='ck_bloqueio_motivo'),
        CheckConstraint('(revogado_por IS NULL) = (revogado_em IS NULL)', name='ck_bloqueio_revogacao'),
        Index('ix_bloqueios_agenda_contexto', 'filial_id', 'barbeiro_id', 'data'),
        ExcludeConstraint(
            ('filial_id', '='), ('barbeiro_id', '='),
            (text("tsrange(data + hora_inicio, data + hora_fim, '[)')"), '&&'),
            using='gist', where=text('revogado_em IS NULL'), name='ex_bloqueios_agenda_intervalo',
        ).ddl_if(dialect='postgresql'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), ForeignKey('filiais.id', ondelete='RESTRICT'), nullable=False)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    data = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fim = Column(Time, nullable=False)
    motivo = Column(Text, nullable=False)
    criado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    revogado_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id', ondelete='RESTRICT'))
    revogado_em = Column(DateTime(timezone=True))
