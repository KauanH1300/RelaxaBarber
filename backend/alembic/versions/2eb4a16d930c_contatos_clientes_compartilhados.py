"""Telefone compartilhado e separação entre e-mail de contato e de login."""
from alembic import op
import sqlalchemy as sa

revision = '2eb4a16d930c'
down_revision = 'd5a812e4c970'
branch_labels = depends_on = None


def upgrade():
    op.execute(r"""
        CREATE FUNCTION public.normalizar_telefone_cliente(valor text) RETURNS text
        LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE SET search_path = pg_catalog AS $$
            SELECT CASE
                WHEN valor !~ '^[0-9+().[:space:]-]+$' THEN NULL
                WHEN digitos ~ '^[1-9][0-9]{9,10}$' THEN '55' || digitos
                WHEN digitos ~ '^[1-9][0-9]{11,14}$' AND digitos !~ '^550' THEN digitos
                ELSE NULL END
            FROM (SELECT regexp_replace(valor, '[^0-9]', '', 'g') AS digitos) AS telefone
        $$
    """)
    op.execute('GRANT EXECUTE ON FUNCTION public.normalizar_telefone_cliente(text) TO relaxabarber_runtime')
    op.add_column('clientes', sa.Column(
        'telefone_normalizado', sa.String(15),
        sa.Computed('public.normalizar_telefone_cliente(telefone)', persisted=True),
    ), schema='public')
    op.create_index('ix_clientes_telefone_normalizado', 'clientes', ['telefone_normalizado'],
                    schema='public', postgresql_where=sa.text('telefone_normalizado IS NOT NULL'))
    op.drop_index('ix_clientes_telefone', table_name='clientes', schema='public')
    op.drop_index('ix_clientes_email', table_name='clientes', schema='public')
    # A conta tem unicidade própria. Preserva a restrição entre fichas de contato.
    op.create_index('ix_clientes_email', 'clientes', ['email'], schema='public', unique=True,
                    postgresql_where=sa.text('NOT conta_ativada'))
    op.execute('GRANT SELECT (telefone_normalizado) ON public.clientes TO relaxabarber_runtime')


def downgrade():
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT telefone FROM public.clientes GROUP BY telefone HAVING count(*) > 1)
                OR EXISTS (SELECT email FROM public.clientes WHERE email IS NOT NULL
                           GROUP BY email HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'Há contatos compartilhados. A reversão exige preservar e revisar esses dados.';
            END IF;
        END $$
    """)
    op.drop_index('ix_clientes_email', table_name='clientes', schema='public')
    op.create_index('ix_clientes_email', 'clientes', ['email'], schema='public', unique=True)
    op.create_index('ix_clientes_telefone', 'clientes', ['telefone'], schema='public', unique=True)
    op.drop_index('ix_clientes_telefone_normalizado', table_name='clientes', schema='public')
    op.drop_column('clientes', 'telefone_normalizado', schema='public')
    op.execute('DROP FUNCTION public.normalizar_telefone_cliente(text)')
