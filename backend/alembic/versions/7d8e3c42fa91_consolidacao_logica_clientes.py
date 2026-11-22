"""Decisões sobre pares de clientes, com auditoria preservada."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '7d8e3c42fa91'
down_revision = '2eb4a16d930c'
branch_labels = depends_on = None


def upgrade():
    def referencia(nome, tabela, **opcoes):
        return sa.Column(nome, UUID(as_uuid=True), sa.ForeignKey(f'public.{tabela}.id', ondelete='RESTRICT'),
                         **opcoes)

    op.create_table('clientes_pares',
        referencia('cliente_a', 'clientes', primary_key=True),
        referencia('cliente_b', 'clientes', primary_key=True),
        referencia('filial_id', 'filiais', nullable=False),
        sa.Column('estado', sa.String(20), nullable=False),
        referencia('principal_id', 'clientes'), referencia('associado_id', 'clientes'),
        sa.Column('versao', UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint('cliente_a < cliente_b', name='ck_clientes_par_ordem'),
        sa.CheckConstraint("estado IN ('encaminhado','diferentes','associado','reaberto')", name='ck_clientes_par_estado'),
        sa.CheckConstraint("""(estado = 'associado' AND principal_id IS NOT NULL AND associado_id IS NOT NULL
            AND ((principal_id = cliente_a AND associado_id = cliente_b) OR
                 (principal_id = cliente_b AND associado_id = cliente_a))) OR
            (estado <> 'associado' AND principal_id IS NULL AND associado_id IS NULL)""",
                           name='ck_clientes_par_associacao'), schema='public')
    op.create_index('uq_clientes_par_associado', 'clientes_pares', ['associado_id'], unique=True, schema='public')
    op.create_index('ix_clientes_par_principal', 'clientes_pares', ['principal_id'], schema='public')
    op.create_table('clientes_decisoes',
        sa.Column('chave', UUID(as_uuid=True), primary_key=True),
        referencia('cliente_a', 'clientes', nullable=False), referencia('cliente_b', 'clientes', nullable=False),
        referencia('filial_id', 'filiais', nullable=False), referencia('ator_id', 'usuarios', nullable=False),
        sa.Column('acao', sa.String(20), nullable=False),
        sa.Column('estado_anterior', sa.String(20), nullable=False),
        sa.Column('estado', sa.String(20), nullable=False),
        referencia('principal_id', 'clientes'),
        sa.Column('metodo', sa.String(40)), sa.Column('justificativa', sa.String(500), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('registrado_em', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema='public')
    for tabela, acoes in (('clientes_pares', ('SELECT', 'INSERT', 'UPDATE')),
                          ('clientes_decisoes', ('SELECT', 'INSERT'))):
        nome = f'public.{tabela}'
        op.execute(f'ALTER TABLE {nome} ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON {nome} FROM PUBLIC, anon, authenticated, service_role, relaxabarber_runtime')
        op.execute(f'GRANT {", ".join(acoes)} ON {nome} TO relaxabarber_runtime')
        for acao in acoes:
            clausula = 'WITH CHECK (true)' if acao == 'INSERT' else 'USING (true)'
            if acao == 'UPDATE':
                clausula += ' WITH CHECK (true)'
            op.execute(f'CREATE POLICY {tabela}_{acao.lower()} ON {nome} FOR {acao} TO relaxabarber_runtime {clausula}')


def downgrade():
    raise NotImplementedError('Preserve a trilha de decisões e reverta as associações pela aplicação.')
