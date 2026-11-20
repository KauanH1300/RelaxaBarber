from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, Uuid, func

from app.db.database import Base


class InsumoServico(Base):
    __tablename__ = 'insumos_servico'
    __table_args__ = (
        ForeignKeyConstraint(['produto_id', 'filial_id'], ['produtos_estoque.id', 'produtos_estoque.filial_id']),
        CheckConstraint('quantidade > 0', name='ck_insumo_servico_quantidade'),
        Index('ix_insumos_servico_produto', 'produto_id'),
    )
    servico_id = Column(Uuid, ForeignKey('servicos.id'), primary_key=True)
    filial_id = Column(Uuid, primary_key=True)
    produto_id = Column(Uuid, primary_key=True)
    quantidade = Column(Numeric(14, 3), nullable=False)


class ConsumoAtendimento(Base):
    __tablename__ = 'consumos_atendimento'
    __table_args__ = (
        ForeignKeyConstraint(['produto_id', 'filial_id'], ['produtos_estoque.id', 'produtos_estoque.filial_id']),
        ForeignKeyConstraint(['agendamento_id', 'filial_id'], ['agendamentos.id', 'agendamentos.filial_id']),
        CheckConstraint('baixada >= 0 AND prevista > 0 AND baixada <= prevista', name='ck_consumo_quantidades'),
        CheckConstraint('(baixada = 0) = (movimento_id IS NULL)', name='ck_consumo_movimento'),
    )
    agendamento_id = Column(Uuid, primary_key=True)
    produto_id = Column(Uuid, primary_key=True)
    filial_id = Column(Uuid, nullable=False)
    nome = Column(String(150), nullable=False)
    unidade = Column(String(20), nullable=False)
    prevista = Column(Numeric(18, 3), nullable=False)
    baixada = Column(Numeric(14, 3), nullable=False)
    movimento_id = Column(Uuid, ForeignKey('movimentos_estoque.id'), unique=True)
    registrado_por = Column(Uuid, ForeignKey('usuarios.id'), nullable=False)
    registrado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    @property
    def nao_baixada(self):
        return self.prevista - self.baixada
