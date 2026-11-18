"""Categorias e marcas opcionais por filial, sem alterar produtos existentes."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'a38f72b96c14'
down_revision = 'e12a46c8179b'
branch_labels = depends_on = None

def upgrade():
    op.execute("""DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='relaxabarber_runtime' AND NOT rolsuper AND NOT rolbypassrls) THEN RAISE EXCEPTION 'relaxabarber_runtime ausente ou privilegiado'; END IF; END $$""")
    spec = spec_from_file_location('financeiro_acl_catalogo_estoque', Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    modulo = module_from_spec(spec); spec.loader.exec_module(modulo)
    for tabela, singular in (('categorias_estoque', 'categoria'), ('marcas_estoque', 'marca')):
        op.create_table(tabela,
            sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
            sa.Column('filial_id', pg.UUID(as_uuid=True), sa.ForeignKey('public.filiais.id'), nullable=False),
            sa.Column('nome', sa.String(100), nullable=False),
            sa.UniqueConstraint('id', 'filial_id', name=f'uq_{singular}_estoque_filial'),
            sa.CheckConstraint("length(btrim(nome)) > 0 AND nome !~ '[[:cntrl:]]'", name=f'ck_{singular}_estoque_nome'), schema='public')
        op.create_index(f'ux_{singular}_estoque_nome', tabela, ['filial_id', sa.text('lower(btrim(nome))')], unique=True, schema='public')
        modulo.proteger_tabela(tabela)
    for coluna, tabela, nome in (('categoria_id','categorias_estoque','categoria'), ('marca_id','marcas_estoque','marca')):
        op.add_column('produtos_estoque', sa.Column(coluna, pg.UUID(as_uuid=True), nullable=True), schema='public')
        op.create_foreign_key(f'fk_produto_{nome}_filial', 'produtos_estoque', tabela, [coluna,'filial_id'], ['id','filial_id'], source_schema='public', referent_schema='public')
    op.execute('GRANT UPDATE (categoria_id, marca_id) ON public.produtos_estoque TO relaxabarber_runtime')

def downgrade():
    raise NotImplementedError('A reversão requer plano que preserve as classificações existentes')
