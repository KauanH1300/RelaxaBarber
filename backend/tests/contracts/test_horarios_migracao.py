"""Valida a DDL PostgreSQL offline; não abre conexão nem aplica migrações."""
from io import StringIO
from pathlib import Path


def test_migracao_aditiva_sem_backfill(isolated_runtime):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    config = Config()
    config.set_main_option('script_location', str(Path(__file__).resolve().parents[2] / 'alembic'))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ['b91e4c7d203a']
    revision = scripts.get_revision('head')
    assert revision.down_revision == 'a15c39d42e68'
    output = StringIO()
    context = MigrationContext.configure(dialect_name='postgresql', opts={
        'as_sql': True, 'output_buffer': output,
    })
    with Operations.context(context):
        revision.module.upgrade()
    sql = output.getvalue()
    assert 'CREATE TABLE public.filial_horarios' in sql
    for name in ('uq_filial_horarios_dia', 'ck_filial_horarios_dia',
                 'ck_filial_horarios_intervalo', 'fk_filial_horarios_filial'):
        assert name in sql
    assert 'REFERENCES public.filiais (id)' in sql
    assert all(word not in sql.upper() for word in ('INSERT ', 'UPDATE ', 'DELETE ', 'ALTER ', 'DROP '))
