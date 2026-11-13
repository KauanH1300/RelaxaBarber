"""Persistência financeira; regras de saldo e autorização pertencem aos serviços."""
import enum
import uuid
from decimal import Decimal, InvalidOperation

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator

from app.db.database import Base


class SituacaoFinanceiraEnum(str, enum.Enum):
    NAO_VERIFICADO = "nao_verificado"
    ABERTO = "aberto"
    FECHADO = "fechado"


class ValorFinanceiro(TypeDecorator):
    """Decimal exato no ORM; rejeita arredondamento silencioso e floats."""
    impl = Numeric(10, 2)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if not isinstance(value, Decimal):
            raise ValueError("Valor financeiro deve ser Decimal")
        try:
            valido = (value.is_finite() and value.copy_abs() <= Decimal("99999999.99")
                      and value == value.quantize(Decimal("0.01")))
        except InvalidOperation:
            valido = False
        if not valido:
            raise ValueError("Valor financeiro fora da faixa ou com fração de centavo")
        return value


class ControleFinanceiroComanda(Base):
    """Ausência do controle significa histórico não verificado, inclusive legado."""
    __tablename__ = "controles_financeiros_comanda"
    __table_args__ = (
        UniqueConstraint("comanda_id", "filial_id", name="uq_controle_financeiro_contexto"),
        ForeignKeyConstraint(["comanda_id", "filial_id"], ["comandas.id", "comandas.filial_id"],
                             name="fk_controle_financeiro_comanda", ondelete="RESTRICT"),
        CheckConstraint("length(trim(motivo)) > 0", name="ck_controle_financeiro_motivo"),
    )
    comanda_id = Column(UUID(as_uuid=True), primary_key=True)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="RESTRICT",
                            name="fk_controle_financeiro_responsavel"), nullable=False)
    motivo = Column(Text, nullable=False)
    comanda = relationship("Comanda", back_populates="controle_financeiro")
    fechamento = relationship("FechamentoFinanceiroComanda", uselist=False, passive_deletes="all")


class PagamentoComanda(Base):
    __tablename__ = "pagamentos_comanda"
    __table_args__ = (
        ForeignKeyConstraint(["comanda_id", "filial_id"],
                             ["controles_financeiros_comanda.comanda_id", "controles_financeiros_comanda.filial_id"],
                             name="fk_pagamento_controle", ondelete="RESTRICT"),
        UniqueConstraint("id", "comanda_id", "filial_id", name="uq_pagamento_contexto"),
        UniqueConstraint("comanda_id", "chave_idempotencia", name="uq_pagamento_idempotencia"),
        CheckConstraint("valor > 0 AND valor <= 99999999.99", name="ck_pagamento_valor"),
        CheckConstraint("forma IN ('dinheiro','pix','debito','credito')", name="ck_pagamento_forma"),
        CheckConstraint("length(fingerprint) = 64", name="ck_pagamento_fingerprint"),
        Index("ix_pagamentos_filial_recebido", "filial_id", "recebido_em"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comanda_id = Column(UUID(as_uuid=True), nullable=False)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    valor = Column(ValorFinanceiro(), nullable=False)
    forma = Column(String(10), nullable=False)
    recebido_em = Column(DateTime(timezone=True), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="RESTRICT",
                            name="fk_pagamento_responsavel"), nullable=False)
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
    fingerprint = Column(String(64), nullable=False)


class EstornoPagamento(Base):
    __tablename__ = "estornos_pagamento"
    __table_args__ = (
        ForeignKeyConstraint(["pagamento_id", "comanda_id", "filial_id"],
                             ["pagamentos_comanda.id", "pagamentos_comanda.comanda_id", "pagamentos_comanda.filial_id"],
                             name="fk_estorno_pagamento_contexto", ondelete="RESTRICT"),
        UniqueConstraint("comanda_id", "chave_idempotencia", name="uq_estorno_idempotencia"),
        CheckConstraint("valor > 0 AND valor <= 99999999.99", name="ck_estorno_valor"),
        CheckConstraint("length(trim(motivo)) > 0", name="ck_estorno_motivo"),
        CheckConstraint("length(fingerprint) = 64", name="ck_estorno_fingerprint"),
        Index("ix_estornos_pagamento", "pagamento_id"),
        Index("ix_estornos_filial_efetivo", "filial_id", "efetivado_em"),
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pagamento_id = Column(UUID(as_uuid=True), nullable=False)
    comanda_id = Column(UUID(as_uuid=True), nullable=False)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    valor = Column(ValorFinanceiro(), nullable=False)
    motivo = Column(Text, nullable=False)
    efetivado_em = Column(DateTime(timezone=True), nullable=False)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="RESTRICT",
                            name="fk_estorno_responsavel"), nullable=False)
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
    fingerprint = Column(String(64), nullable=False)


class FechamentoFinanceiroComanda(Base):
    """Um fechamento definitivo por comanda, com snapshot de quitação."""
    __tablename__ = "fechamentos_financeiros_comanda"
    __table_args__ = (
        ForeignKeyConstraint(["comanda_id", "filial_id"],
                             ["controles_financeiros_comanda.comanda_id", "controles_financeiros_comanda.filial_id"],
                             name="fk_fechamento_controle", ondelete="RESTRICT"),
        CheckConstraint("total >= 0 AND total <= 99999999.99", name="ck_fechamento_total"),
        CheckConstraint("recebido_liquido >= 0 AND recebido_liquido <= 99999999.99",
                        name="ck_fechamento_recebido"),
        CheckConstraint("total = recebido_liquido", name="ck_fechamento_quitacao"),
        CheckConstraint("total <> 0 OR (motivo IS NOT NULL AND length(trim(motivo)) > 0)",
                        name="ck_fechamento_zero_motivo"),
        CheckConstraint("length(fingerprint) = 64", name="ck_fechamento_fingerprint"),
        Index("ix_fechamentos_filial_registro", "filial_id", "registrado_em"),
    )
    comanda_id = Column(UUID(as_uuid=True), primary_key=True)
    filial_id = Column(UUID(as_uuid=True), nullable=False)
    total = Column(ValorFinanceiro(), nullable=False)
    recebido_liquido = Column(ValorFinanceiro(), nullable=False)
    motivo = Column(Text, nullable=True)
    registrado_em = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    registrado_por = Column(UUID(as_uuid=True), ForeignKey("usuarios.id", ondelete="RESTRICT",
                            name="fk_fechamento_responsavel"), nullable=False)
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
    fingerprint = Column(String(64), nullable=False)
