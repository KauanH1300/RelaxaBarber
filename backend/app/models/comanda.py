import uuid
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, ForeignKeyConstraint, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Comanda(Base):
    __tablename__ = "comandas"
    __table_args__ = (
        CheckConstraint("(tipo = 'agendada' AND agendamento_id IS NOT NULL AND cliente_id IS NOT NULL AND barbeiro_id IS NOT NULL) OR (tipo = 'avulsa' AND agendamento_id IS NULL)", name='ck_comanda_tipo_contexto'),
        UniqueConstraint('id', 'tipo', name='uq_comanda_id_tipo'),
        UniqueConstraint('filial_id', 'chave_abertura', name='uq_comanda_abertura_filial'),
        CheckConstraint("(chave_abertura IS NULL AND abertura_por IS NULL) OR (tipo = 'avulsa' AND chave_abertura IS NOT NULL AND abertura_por IS NOT NULL)", name='ck_comanda_abertura_avulsa'),
        CheckConstraint("desconto_tipo IN ('nenhum','valor','percentual') AND desconto_valor >= 0 AND desconto_valor <= 99999999.99 AND (desconto_tipo <> 'percentual' OR desconto_valor <= 100) AND (desconto_tipo <> 'nenhum' OR desconto_valor = 0)", name='ck_comanda_desconto'),
        CheckConstraint('versao_itens >= 0', name='ck_comanda_versao_itens'),
        UniqueConstraint("id", "filial_id", name="uq_comandas_id_filial"),
        ForeignKeyConstraint(
            ["agendamento_id", "filial_id", "cliente_id", "barbeiro_id"],
            ["agendamentos.id", "agendamentos.filial_id", "agendamentos.cliente_id", "agendamentos.barbeiro_id"],
            name="fk_comandas_contexto_agendamento",
            onupdate="CASCADE",
        ),
        Index("ix_comandas_filial_status", "filial_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filial_id = Column(UUID(as_uuid=True), ForeignKey("filiais.id", name="fk_comandas_filial"), nullable=False)
    filial = relationship("Filial")
    tipo = Column(String(12), nullable=False, server_default='agendada', default='agendada')
    chave_abertura = Column(UUID(as_uuid=True), nullable=True)
    abertura_por = Column(UUID(as_uuid=True), ForeignKey('usuarios.id'), nullable=True)
    agendamento_id = Column(UUID(as_uuid=True), ForeignKey("agendamentos.id"), unique=True, nullable=True)
    cliente_id = Column(UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=True)
    barbeiro_id = Column(UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=True)
    data_abertura = Column(DateTime(timezone=True), nullable=True)
    data_fechamento = Column(DateTime(timezone=True), nullable=True)
    valor_total = Column(Numeric(10, 2), nullable=False, default=0)
    comissoes_ativas = Column(Boolean, nullable=False, default=False, server_default=text('false'))
    versao_itens = Column(Integer, nullable=False, default=0, server_default=text('0'))
    desconto_tipo = Column(String(12), nullable=False, default='nenhum', server_default='nenhum')
    desconto_valor = Column(Numeric(10, 2), nullable=False, default=0, server_default=text('0'))
    status = Column(String, nullable=False, default="pendente")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    itens = relationship("ItemComanda", back_populates="comanda", cascade="all, delete-orphan", foreign_keys="ItemComanda.comanda_id")
    cancelamento = relationship('CancelamentoComanda', uselist=False, passive_deletes='all')
    controle_financeiro = relationship("ControleFinanceiroComanda", back_populates="comanda",
                                      uselist=False, passive_deletes="all")

    @property
    def situacao_financeira(self):
        from app.models.financeiro import SituacaoFinanceiraEnum
        if self.controle_financeiro is None:
            return SituacaoFinanceiraEnum.NAO_VERIFICADO
        if self.controle_financeiro.fechamento is not None:
            return SituacaoFinanceiraEnum.FECHADO
        return SituacaoFinanceiraEnum.ABERTO

class ItemComanda(Base):
    __tablename__ = "itens_comanda"
    __table_args__ = (
        ForeignKeyConstraint(['comanda_id', 'comanda_tipo'], ['comandas.id', 'comandas.tipo'], name='fk_item_comanda_tipo'),
        ForeignKeyConstraint(['comanda_id', 'filial_id'], ['comandas.id', 'comandas.filial_id'], name='fk_item_comanda_filial'),
        ForeignKeyConstraint(['produto_id', 'filial_id'], ['produtos_estoque.id', 'produtos_estoque.filial_id'], name='fk_item_produto_filial'),
        ForeignKeyConstraint(['comissao_profissional_id', 'filial_id'], ['usuario_filiais.usuario_id', 'usuario_filiais.filial_id'], name='fk_item_comissao_profissional_filial'),
        CheckConstraint("comanda_tipo = 'agendada' OR (comanda_tipo = 'avulsa' AND tipo = 'produto' AND servico_id IS NULL AND produto_id IS NOT NULL AND filial_id IS NOT NULL AND quantidade > 0 AND preco_unitario >= 0 AND custo_snapshot IS NOT NULL AND custo_snapshot >= 0 AND comissao_percentual_snapshot IS NOT NULL AND comissao_percentual_snapshot BETWEEN 0 AND 100)", name='ck_item_avulso_produto'),
        UniqueConstraint('id', 'comanda_id', name='uq_itens_comanda_contexto'),
        UniqueConstraint('id', 'comanda_id', 'produto_id', 'filial_id', name='uq_item_comanda_produto_filial'),
        CheckConstraint("desconto_tipo IN ('nenhum','valor','percentual','cortesia') AND desconto_valor >= 0 AND desconto_valor <= 99999999.99 AND (desconto_tipo <> 'percentual' OR desconto_valor <= 100) AND (desconto_tipo NOT IN ('nenhum','cortesia') OR desconto_valor = 0) AND (desconto_tipo <> 'valor' OR desconto_valor <= quantidade * preco_unitario)", name='ck_item_desconto'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comanda_id = Column(UUID(as_uuid=True), ForeignKey("comandas.id"), nullable=False)
    tipo = Column(String, nullable=False)  # "servico" ou "produto"
    comanda_tipo = Column(String(12), nullable=False, default='agendada', server_default='agendada')
    filial_id = Column(UUID(as_uuid=True), nullable=True)
    produto_id = Column(UUID(as_uuid=True), nullable=True)
    custo_snapshot = Column(Numeric(12, 2), nullable=True)
    comissao_percentual_snapshot = Column(Numeric(5, 2), nullable=True)
    comissao_profissional_id = Column(UUID(as_uuid=True), nullable=True)
    servico_id = Column(UUID(as_uuid=True), ForeignKey("servicos.id"), nullable=True)
    descricao = Column(String, nullable=False)
    quantidade = Column(Integer, nullable=False, default=1)
    ativo = Column(Boolean, nullable=False, default=True, server_default=text('true'))
    preco_unitario = Column(Numeric(10, 2), nullable=False)
    desconto_tipo = Column(String(12), nullable=False, default='nenhum', server_default='nenhum')
    desconto_valor = Column(Numeric(10, 2), nullable=False, default=0, server_default=text('0'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    comanda = relationship("Comanda", back_populates="itens", foreign_keys=[comanda_id])
