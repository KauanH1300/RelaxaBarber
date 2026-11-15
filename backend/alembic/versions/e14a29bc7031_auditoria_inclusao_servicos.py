"""Auditoria/idempotência aditivas de inclusão de serviços; sem backfill.

Revision ID: e14a29bc7031
Revises: d93a7e2f610c
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e14a29bc7031'
down_revision = 'd93a7e2f610c'
branch_labels = depends_on = None


def upgrade():
    op.create_table('inclusoes_servicos_comanda',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('comanda_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filial_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.itens_comanda.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_por', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('chave_idempotencia', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('total_resultante', sa.Numeric(10, 2), nullable=False),
        sa.ForeignKeyConstraint(['comanda_id', 'filial_id'], ['public.comandas.id', 'public.comandas.filial_id'], name='fk_inclusao_contexto', ondelete='RESTRICT'),
        sa.UniqueConstraint('comanda_id', 'chave_idempotencia', name='uq_inclusao_idempotencia'),
        sa.UniqueConstraint('item_id', name='uq_inclusao_item'),
        sa.CheckConstraint('length(fingerprint) = 64', name='ck_inclusao_fingerprint'),
        sa.CheckConstraint('total_resultante >= 0 AND total_resultante <= 99999999.99', name='ck_inclusao_total'), schema='public')
    op.execute('CREATE TRIGGER inclusao_carimbo BEFORE INSERT ON public.inclusoes_servicos_comanda FOR EACH ROW EXECUTE FUNCTION public.financeiro_carimbar_registro()')
    op.execute('CREATE TRIGGER inclusao_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.inclusoes_servicos_comanda FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()')
    # Mesmas proteções de ACL/RLS auditadas pela migração financeira anterior.
    from importlib.util import spec_from_file_location, module_from_spec
    from pathlib import Path
    spec = spec_from_file_location('financeiro_anterior', Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    modulo = module_from_spec(spec)
    spec.loader.exec_module(modulo)
    modulo.proteger_tabela('inclusoes_servicos_comanda')


def downgrade():
    op.execute('LOCK TABLE public.inclusoes_servicos_comanda IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.inclusoes_servicos_comanda) THEN
        RAISE EXCEPTION 'Downgrade bloqueado: ha auditoria a preservar'; END IF; END $$""")
    op.drop_table('inclusoes_servicos_comanda', schema='public')
