"""Cancelamento direto de comandas vazias, com auditoria imutável."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'd17a60c28e94'
down_revision = 'ab72d90e613f'
branch_labels = depends_on = None


def upgrade():
    op.create_table('cancelamentos_comanda',
        sa.Column('comanda_id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('filial_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('registrado_por', pg.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('chave_idempotencia', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('resultado', pg.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['comanda_id','filial_id'], ['public.comandas.id','public.comandas.filial_id'], ondelete='RESTRICT'),
        sa.CheckConstraint('length(trim(motivo))>0', name='ck_cancelamento_comanda_motivo'),
        sa.CheckConstraint('length(fingerprint)=64', name='ck_cancelamento_comanda_fingerprint'), schema='public')
    spec = spec_from_file_location('financeiro_acl', Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    modulo = module_from_spec(spec); spec.loader.exec_module(modulo)
    modulo.proteger_tabela('cancelamentos_comanda')
    op.execute('CREATE TRIGGER cancelamentos_comanda_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.cancelamentos_comanda FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()')
    op.execute('CREATE TRIGGER cancelamento_comanda_carimbo BEFORE INSERT ON public.cancelamentos_comanda FOR EACH ROW EXECUTE FUNCTION public.itens_carimbar_alteracao()')


def downgrade():
    raise NotImplementedError('Preservar cancelamentos: reversão exige plano próprio')
