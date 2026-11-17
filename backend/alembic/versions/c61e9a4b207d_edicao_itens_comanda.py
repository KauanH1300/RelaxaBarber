"""Edição auditável e remoção lógica, sem apagar ou reescrever auditoria anterior."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = 'c61e9a4b207d'
down_revision = 'f05c82d931ae'
branch_labels = depends_on = None


def upgrade():
    op.add_column('comandas', sa.Column('versao_itens', sa.Integer(), nullable=False, server_default='0'), schema='public')
    op.create_check_constraint('ck_comanda_versao_itens', 'comandas', 'versao_itens >= 0', schema='public')
    op.add_column('itens_comanda', sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()), schema='public')
    op.create_table('respostas_inclusoes_comanda',
        sa.Column('inclusao_id', pg.UUID(as_uuid=True), sa.ForeignKey('public.inclusoes_servicos_comanda.id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('resposta', pg.JSONB(), nullable=False), schema='public')
    # Congela as respostas históricas antes de permitir qualquer edição. INSERT
    # em tabela nova; a auditoria de inclusão existente permanece intocada.
    op.execute("""INSERT INTO public.respostas_inclusoes_comanda(inclusao_id,resposta)
        SELECT a.id,jsonb_build_object('item',jsonb_build_object(
            'id',i.id,'tipo',i.tipo,'servico_id',i.servico_id,'descricao',i.descricao,
            'quantidade',i.quantidade,'preco_unitario',i.preco_unitario::text,
            'subtotal',(i.quantidade*i.preco_unitario)::text,'ativo',true),
            'total',a.total_resultante::text,'registrado_em',a.registrado_em,
            'registrado_por',a.registrado_por,'chave_idempotencia',a.chave_idempotencia)
        FROM public.inclusoes_servicos_comanda a JOIN public.itens_comanda i ON i.id=a.item_id""")
    op.create_table('alteracoes_itens_comanda',
        sa.Column('id', pg.UUID(as_uuid=True), primary_key=True),
        sa.Column('comanda_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('filial_id', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('item_id', pg.UUID(as_uuid=True), sa.ForeignKey('public.itens_comanda.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_por', pg.UUID(as_uuid=True), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('chave_idempotencia', pg.UUID(as_uuid=True), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('resultado', pg.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['comanda_id','filial_id'], ['public.comandas.id','public.comandas.filial_id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('comanda_id','chave_idempotencia',name='uq_alteracao_item_idempotencia'),
        sa.CheckConstraint('length(fingerprint)=64',name='ck_alteracao_item_fingerprint'),
        sa.CheckConstraint('length(trim(motivo))>0',name='ck_alteracao_item_motivo'),schema='public')
    spec = spec_from_file_location('financeiro_acl', Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    modulo = module_from_spec(spec); spec.loader.exec_module(modulo)
    for table in ['respostas_inclusoes_comanda','alteracoes_itens_comanda']:
        modulo.proteger_tabela(table)
        op.execute(f'CREATE TRIGGER {table}_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.{table} FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()')
    op.execute("""CREATE FUNCTION public.itens_carimbar_alteracao() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
            NEW.registrado_em := clock_timestamp();
            NEW.resultado := jsonb_set(NEW.resultado,'{registrado_em}',to_jsonb(NEW.registrado_em));
            RETURN NEW;
        END $$""")
    op.execute('REVOKE ALL ON FUNCTION public.itens_carimbar_alteracao() FROM PUBLIC')
    op.execute('CREATE TRIGGER alteracao_item_carimbo BEFORE INSERT ON public.alteracoes_itens_comanda FOR EACH ROW EXECUTE FUNCTION public.itens_carimbar_alteracao()')
    op.execute('GRANT UPDATE (versao_itens,valor_total) ON public.comandas TO relaxabarber_runtime')
    op.execute('GRANT UPDATE (quantidade,servico_id,descricao,preco_unitario,ativo) ON public.itens_comanda TO relaxabarber_runtime')


def downgrade():
    raise NotImplementedError('Preservar auditoria e remoções lógicas; reversão exige plano próprio')
