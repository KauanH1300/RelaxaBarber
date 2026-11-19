"""Fechamentos e repasses imutáveis de comissão, sem alteração de dados anteriores."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'f6c28d19a470'
down_revision = 'c8d47a9b2e31'
branch_labels = depends_on = None


def upgrade():
    u = UUID(as_uuid=True)
    op.create_unique_constraint('uq_evento_repasse_contexto', 'eventos_comissao', ['id','item_id','filial_id','profissional_id'], schema='public')
    op.create_table('fechamentos_repasse',
        sa.Column('id',u,primary_key=True), sa.Column('filial_id',u,nullable=False), sa.Column('profissional_id',u,nullable=False),
        sa.Column('inicio',sa.Date,nullable=False),sa.Column('fim',sa.Date,nullable=False),sa.Column('valor',sa.Numeric(12,2),nullable=False),
        sa.Column('registrado_por',u,sa.ForeignKey('public.usuarios.id',ondelete='RESTRICT'),nullable=False),sa.Column('registrado_em',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('chave',u,nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.ForeignKeyConstraint(['profissional_id','filial_id'],['public.usuario_filiais.usuario_id','public.usuario_filiais.filial_id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('id','filial_id','profissional_id',name='uq_fechamento_repasse_contexto'),sa.UniqueConstraint('filial_id','chave',name='uq_fechamento_repasse_chave'),
        sa.CheckConstraint('inicio <= fim AND valor > 0 AND length(fingerprint)=64',name='ck_fechamento_repasse_valido'),schema='public')
    op.create_table('parcelas_repasse',
        sa.Column('id',u,primary_key=True),sa.Column('fechamento_id',u,nullable=False),sa.Column('filial_id',u,nullable=False),sa.Column('profissional_id',u,nullable=False),
        sa.Column('item_id',u,nullable=False),sa.Column('evento_id',u,nullable=False),sa.Column('origem',sa.Date,nullable=False),sa.Column('valor',sa.Numeric(12,2),nullable=False),
        sa.ForeignKeyConstraint(['fechamento_id','filial_id','profissional_id'],['public.fechamentos_repasse.id','public.fechamentos_repasse.filial_id','public.fechamentos_repasse.profissional_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['evento_id','item_id','filial_id','profissional_id'],['public.eventos_comissao.id','public.eventos_comissao.item_id','public.eventos_comissao.filial_id','public.eventos_comissao.profissional_id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('id','fechamento_id',name='uq_parcela_repasse_contexto'),sa.UniqueConstraint('fechamento_id','item_id',name='uq_fechamento_repasse_item'),sa.CheckConstraint('valor > 0',name='ck_parcela_repasse_valor'),schema='public')
    op.create_table('pagamentos_repasse',
        sa.Column('id',u,primary_key=True),sa.Column('fechamento_id',u,nullable=False),sa.Column('filial_id',u,nullable=False),sa.Column('profissional_id',u,nullable=False),
        sa.Column('valor',sa.Numeric(12,2),nullable=False),sa.Column('metodo',sa.String(15),nullable=False),sa.Column('data_pagamento',sa.DateTime(timezone=True),nullable=False),
        sa.Column('registrado_por',u,sa.ForeignKey('public.usuarios.id',ondelete='RESTRICT'),nullable=False),sa.Column('registrado_em',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('chave',u,nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.ForeignKeyConstraint(['fechamento_id','filial_id','profissional_id'],['public.fechamentos_repasse.id','public.fechamentos_repasse.filial_id','public.fechamentos_repasse.profissional_id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('id','fechamento_id',name='uq_pagamento_repasse_contexto'),sa.UniqueConstraint('fechamento_id','chave',name='uq_pagamento_repasse_chave'),
        sa.CheckConstraint("valor > 0 AND metodo IN ('pix','dinheiro','transferencia') AND length(fingerprint)=64",name='ck_pagamento_repasse_valido'),schema='public')
    op.create_table('alocacoes_repasse',sa.Column('pagamento_id',u,nullable=False),sa.Column('parcela_id',u,nullable=False),sa.Column('fechamento_id',u,nullable=False),sa.Column('valor',sa.Numeric(12,2),nullable=False),
        sa.PrimaryKeyConstraint('pagamento_id','parcela_id'),sa.ForeignKeyConstraint(['pagamento_id','fechamento_id'],['public.pagamentos_repasse.id','public.pagamentos_repasse.fechamento_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['parcela_id','fechamento_id'],['public.parcelas_repasse.id','public.parcelas_repasse.fechamento_id'],ondelete='RESTRICT'),sa.CheckConstraint('valor > 0',name='ck_alocacao_repasse_valor'),schema='public')
    op.create_table('estornos_repasse',sa.Column('id',u,primary_key=True),sa.Column('pagamento_id',u,nullable=False),sa.Column('fechamento_id',u,nullable=False),sa.Column('valor',sa.Numeric(12,2),nullable=False),sa.Column('motivo',sa.Text,nullable=False),
        sa.Column('registrado_por',u,sa.ForeignKey('public.usuarios.id',ondelete='RESTRICT'),nullable=False),sa.Column('registrado_em',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column('chave',u,nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.ForeignKeyConstraint(['pagamento_id','fechamento_id'],['public.pagamentos_repasse.id','public.pagamentos_repasse.fechamento_id'],ondelete='RESTRICT'),sa.UniqueConstraint('id','pagamento_id',name='uq_estorno_repasse_contexto'),sa.UniqueConstraint('fechamento_id','chave',name='uq_estorno_repasse_chave'),
        sa.CheckConstraint('valor > 0 AND length(btrim(motivo)) > 0 AND length(fingerprint)=64',name='ck_estorno_repasse_valido'),schema='public')
    op.create_table('alocacoes_estorno_repasse',sa.Column('estorno_id',u,nullable=False),sa.Column('pagamento_id',u,nullable=False),sa.Column('parcela_id',u,nullable=False),sa.Column('valor',sa.Numeric(12,2),nullable=False),
        sa.PrimaryKeyConstraint('estorno_id','parcela_id'),sa.ForeignKeyConstraint(['estorno_id','pagamento_id'],['public.estornos_repasse.id','public.estornos_repasse.pagamento_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['pagamento_id','parcela_id'],['public.alocacoes_repasse.pagamento_id','public.alocacoes_repasse.parcela_id'],ondelete='RESTRICT'),sa.CheckConstraint('valor > 0',name='ck_alocacao_estorno_repasse_valor'),schema='public')
    spec=spec_from_file_location('acl_repasse',Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    module=module_from_spec(spec);spec.loader.exec_module(module)
    for tabela in ('fechamentos_repasse','parcelas_repasse','pagamentos_repasse','alocacoes_repasse','estornos_repasse','alocacoes_estorno_repasse'):
        module.proteger_tabela(tabela)
        op.execute(f'CREATE TRIGGER {tabela}_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.{tabela} FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()')
    for tabela in ('fechamentos_repasse','pagamentos_repasse','estornos_repasse'):
        op.execute(f'CREATE TRIGGER {tabela}_carimbo BEFORE INSERT ON public.{tabela} FOR EACH ROW EXECUTE FUNCTION public.financeiro_carimbar_registro()')


def downgrade():
    raise NotImplementedError('Reversão exige preservar os repasses e sua auditoria')
