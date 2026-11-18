"""Percentuais de produtos e exceções por profissional e filial."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
revision = 'e12a46c8179b'
down_revision = 'e70c15a9f321'
branch_labels = depends_on = None

def upgrade():
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='relaxabarber_runtime'
                       AND NOT rolsuper AND NOT rolbypassrls) THEN
            RAISE EXCEPTION 'relaxabarber_runtime ausente ou privilegiado';
        END IF;
    END $$""")
    # Falha sem modificar dados se algum percentual legado for inválido.
    op.create_check_constraint('ck_servico_comissao','servicos','comissao_padrao >= 0 AND comissao_padrao <= 100',schema='public')
    op.add_column('produtos_estoque', sa.Column('comissao_padrao', sa.Numeric(5,2), nullable=False, server_default='0'), schema='public')
    op.create_check_constraint('ck_produto_comissao','produtos_estoque','comissao_padrao >= 0 AND comissao_padrao <= 100',schema='public')
    op.execute('GRANT UPDATE (comissao_padrao) ON public.produtos_estoque TO relaxabarber_runtime')
    op.create_table('excecoes_comissao',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True), sa.Column('filial_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('profissional_id',pg.UUID(as_uuid=True),nullable=False), sa.Column('servico_id',pg.UUID(as_uuid=True),sa.ForeignKey('public.servicos.id',ondelete='RESTRICT')),
        sa.Column('produto_id',pg.UUID(as_uuid=True)), sa.Column('percentual',sa.Numeric(5,2),nullable=False),
        sa.Column('ativo',sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column('atualizado_por',pg.UUID(as_uuid=True),sa.ForeignKey('public.usuarios.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('atualizado_em',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['profissional_id','filial_id'],['public.usuario_filiais.usuario_id','public.usuario_filiais.filial_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['produto_id','filial_id'],['public.produtos_estoque.id','public.produtos_estoque.filial_id'],ondelete='RESTRICT'),
        sa.UniqueConstraint('filial_id','profissional_id','servico_id',name='uq_comissao_excecao_servico'),
        sa.UniqueConstraint('filial_id','profissional_id','produto_id',name='uq_comissao_excecao_produto'),
        sa.CheckConstraint('(servico_id IS NULL) <> (produto_id IS NULL)',name='ck_comissao_excecao_item'),
        sa.CheckConstraint('percentual >= 0 AND percentual <= 100',name='ck_comissao_excecao_percentual'), schema='public')
    spec=spec_from_file_location('financeiro_acl_comissao',Path(__file__).with_name('d93a7e2f610c_persistencia_financeira.py'))
    module=module_from_spec(spec);spec.loader.exec_module(module);module.proteger_tabela('excecoes_comissao')
    op.execute('GRANT UPDATE (percentual,ativo,atualizado_por,atualizado_em) ON public.excecoes_comissao TO relaxabarber_runtime')
    op.execute('CREATE POLICY comissao_runtime_update ON public.excecoes_comissao FOR UPDATE TO relaxabarber_runtime USING (true) WITH CHECK (true)')


    op.add_column('comandas', sa.Column('comissoes_ativas',sa.Boolean(),nullable=False,server_default=sa.false()),schema='public')
    op.create_unique_constraint('uq_itens_comanda_contexto','itens_comanda',['id','comanda_id'],schema='public')
    op.create_table('comissoes_item',
        sa.Column('item_id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('comanda_id',pg.UUID(as_uuid=True),nullable=False), sa.Column('filial_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('profissional_id',pg.UUID(as_uuid=True),sa.ForeignKey('public.usuarios.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('servico_id',pg.UUID(as_uuid=True),sa.ForeignKey('public.servicos.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('percentual',sa.Numeric(5,2),nullable=False),sa.Column('origem',sa.String(12),nullable=False),
        sa.ForeignKeyConstraint(['comanda_id','filial_id'],['public.comandas.id','public.comandas.filial_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['item_id','comanda_id'],['public.itens_comanda.id','public.itens_comanda.comanda_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['profissional_id','filial_id'],['public.usuario_filiais.usuario_id','public.usuario_filiais.filial_id'],ondelete='RESTRICT'),
        sa.CheckConstraint('percentual >= 0 AND percentual <= 100',name='ck_comissao_item_percentual'),
        sa.CheckConstraint("origem IN ('padrao','excecao')",name='ck_comissao_item_origem'),schema='public')
    op.create_table('eventos_comissao',
        sa.Column('id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('ordem',sa.BigInteger(),sa.Identity(),nullable=False,unique=True),
        sa.Column('item_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('comanda_id',pg.UUID(as_uuid=True),nullable=False),sa.Column('filial_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('profissional_id',pg.UUID(as_uuid=True),sa.ForeignKey('public.usuarios.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('servico_id',pg.UUID(as_uuid=True),sa.ForeignKey('public.servicos.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('percentual',sa.Numeric(5,2),nullable=False),sa.Column('origem_percentual',sa.String(12),nullable=False),
        sa.Column('base',sa.Numeric(12,2),nullable=False),sa.Column('gerada',sa.Numeric(12,2),nullable=False),
        sa.Column('liberada',sa.Numeric(12,2),nullable=False),sa.Column('paga',sa.Numeric(12,2),nullable=False,server_default='0'),
        sa.Column('operacao',sa.String(30),nullable=False),sa.Column('chave_operacao',pg.UUID(as_uuid=True)),
        sa.Column('registrado_por',pg.UUID(as_uuid=True),sa.ForeignKey('public.usuarios.id',ondelete='RESTRICT')),
        sa.Column('registrado_em',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['comanda_id','filial_id'],['public.comandas.id','public.comandas.filial_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['item_id','comanda_id'],['public.itens_comanda.id','public.itens_comanda.comanda_id'],ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['profissional_id','filial_id'],['public.usuario_filiais.usuario_id','public.usuario_filiais.filial_id'],ondelete='RESTRICT'),
        sa.CheckConstraint('percentual >= 0 AND percentual <= 100 AND base >= 0 AND gerada >= 0 AND liberada >= 0 AND liberada <= gerada AND paga >= 0',name='ck_evento_comissao_valores'),
        sa.CheckConstraint("origem_percentual IN ('padrao','excecao')",name='ck_evento_comissao_origem'),
        sa.UniqueConstraint('item_id','operacao','chave_operacao',name='uq_evento_comissao_operacao'),schema='public')
    op.create_index('ix_eventos_comissao_comanda','eventos_comissao',['comanda_id','ordem'],schema='public')
    op.execute("REVOKE ALL ON SEQUENCE public.eventos_comissao_ordem_seq FROM PUBLIC")
    op.execute("""DO $$ DECLARE papel text; BEGIN
        FOREACH papel IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=papel) THEN
                EXECUTE format('REVOKE ALL ON SEQUENCE public.eventos_comissao_ordem_seq FROM %I', papel);
            END IF;
        END LOOP;
    END $$""")
    op.execute('REVOKE ALL ON SEQUENCE public.eventos_comissao_ordem_seq FROM relaxabarber_runtime')
    op.execute('GRANT USAGE ON SEQUENCE public.eventos_comissao_ordem_seq TO relaxabarber_runtime')
    op.execute("""DO $$ DECLARE papel text; BEGIN
        FOREACH papel IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname=papel) AND
               (has_sequence_privilege(papel,'public.eventos_comissao_ordem_seq','USAGE') OR
                has_sequence_privilege(papel,'public.eventos_comissao_ordem_seq','SELECT') OR
                has_sequence_privilege(papel,'public.eventos_comissao_ordem_seq','UPDATE')) THEN
                RAISE EXCEPTION 'Privilégio herdado indevido sobre sequência de comissão';
            END IF;
        END LOOP;
        IF has_sequence_privilege('relaxabarber_runtime','public.eventos_comissao_ordem_seq','UPDATE') OR
           has_sequence_privilege('relaxabarber_runtime','public.eventos_comissao_ordem_seq','SELECT') THEN
            RAISE EXCEPTION 'Privilégio indevido sobre sequência de comissão';
        END IF;
    END $$""")
    for table in ('comissoes_item','eventos_comissao'): module.proteger_tabela(table)
    op.execute('GRANT UPDATE (profissional_id,servico_id,percentual,origem) ON public.comissoes_item TO relaxabarber_runtime')
    op.execute('CREATE POLICY comissao_item_runtime_update ON public.comissoes_item FOR UPDATE TO relaxabarber_runtime USING (true) WITH CHECK (true)')
    op.execute('CREATE TRIGGER eventos_comissao_imutavel BEFORE UPDATE OR DELETE OR TRUNCATE ON public.eventos_comissao FOR EACH STATEMENT EXECUTE FUNCTION public.financeiro_impedir_mutacao()')

def downgrade():
    raise NotImplementedError('Preservar configurações de comissão exige plano de reversão próprio')
