"""Carrega a configuração real com fábrica interceptada; nenhum banco externo."""
from pathlib import Path
import runpy
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize('url,isolation', [
    ('postgresql+psycopg2://ficticio@127.0.0.1/teste', 'READ COMMITTED'),
    ('postgresql://ficticio@127.0.0.1/teste', 'READ COMMITTED'),
    ('sqlite+pysqlite:///:memory:', None),
])
def test_engine_real_define_isolamento_antes_da_sessao(isolated_runtime, monkeypatch, url, isolation):
    import sqlalchemy
    import dotenv
    factory = MagicMock()
    monkeypatch.setattr(sqlalchemy, 'create_engine', factory)
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **kw: False)
    monkeypatch.setenv('DATABASE_URL', url)
    runtime = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'app/db/database.py'))
    expected = {'hide_parameters': True}
    if isolation:
        expected['isolation_level'] = isolation
    factory.assert_called_once_with(url, **expected)
    assert runtime['SessionLocal'].kw['bind'] is factory.return_value
    factory.return_value.connect.assert_not_called()


def test_falha_configuracao_nao_expoe_url(isolated_runtime, monkeypatch):
    import sqlalchemy
    import dotenv
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *a, **kw: False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://ficticio@127.0.0.1/teste')
    def falhar(*a, **kw):
        raise ValueError('falha interna sintetica')
    monkeypatch.setattr(sqlalchemy, 'create_engine', falhar)
    with pytest.raises(RuntimeError, match='Não foi possível configurar a conexão com o banco') as error:
        runpy.run_path(str(Path(__file__).resolve().parents[2] / 'app/db/database.py'))
    assert error.value.__suppress_context__
