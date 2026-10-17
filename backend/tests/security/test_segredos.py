"""Regressão da contenção: somente valores fictícios, sem banco externo."""
import io
import logging
import os
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
FAKE_PASSWORD = 'segredo-ficticio-%:@/com-espaco'
FAKE_URL = 'postgresql+psycopg2://operador:segredo-ficticio-%25%3A%40%2Fcom-espaco@localhost/db?sslrootcert=%2Fca.crt'


@pytest.fixture
def safe_logs(monkeypatch):
    from app.core.logging import install_safe_logging
    factory = logging.getLogRecordFactory()
    hook = sys.excepthook
    import threading
    thread_hook = threading.excepthook
    unraisable_hook = sys.unraisablehook
    monkeypatch.setenv('DATABASE_URL', FAKE_URL)
    monkeypatch.setenv('PGPASSWORD', FAKE_PASSWORD)
    install_safe_logging()
    yield
    logging.setLogRecordFactory(factory)
    sys.excepthook = hook
    threading.excepthook = thread_hook
    sys.unraisablehook = unraisable_hook


def test_logger_independente_argumentos_e_excecao(safe_logs):
    stream = io.StringIO()
    logger = logging.getLogger('terceiro.independente')
    handler = logging.StreamHandler(stream)
    logger.addHandler(handler)
    old = logger.propagate
    logger.propagate = False
    try:
        logger.error('Falha conexão=%s senha=%s', FAKE_URL, FAKE_PASSWORD)
        try:
            raise ValueError(FAKE_PASSWORD + FAKE_URL)
        except ValueError:
            logger.exception('Falha operacional')
    finally:
        logger.removeHandler(handler)
        logger.propagate = old
    output = stream.getvalue()
    assert FAKE_PASSWORD not in output
    assert FAKE_URL not in output
    assert 'postgresql' not in output
    assert 'ValueError' in output
    assert 'test_logger_independente' in output


@pytest.mark.parametrize('message', [
    "password='senha desconhecida com espaços'",
    'password="senha desconhecida com espaços"',
    'password=senha-desconhecida',
    "{'senha': 'senha-desconhecida'}",
    'postgresql://outro:senha-desconhecida@localhost/base',
])
def test_formatos_de_driver_sem_depender_do_secret_conhecido(message):
    from app.core.logging import sanitize
    assert 'desconhecida' not in sanitize(message)


def test_instalacao_idempotente(safe_logs):
    from app.core.logging import install_safe_logging
    factory = logging.getLogRecordFactory()
    install_safe_logging()
    assert logging.getLogRecordFactory() is factory


def test_senha_com_espacos_e_variantes_codificadas_sem_fragmentos(monkeypatch):
    from app.core.logging import sanitize
    from urllib.parse import quote, quote_plus
    password = 'prefixo-distinto% sufixo-distinto'
    monkeypatch.setenv('PGPASSWORD', password)
    for variant in (password, quote(password, safe=''), quote_plus(password)):
        # Inclui uma URL mal codificada para demonstrar que nem seu sufixo vaza.
        output = sanitize('postgresql://operador:' + variant + '@localhost/base')
        assert 'prefixo-distinto' not in output
        assert 'sufixo-distinto' not in output


@pytest.mark.parametrize('offline', [True, False])
def test_alembic_nao_passa_url_ao_configparser(monkeypatch, offline, models):
    from alembic import context
    from alembic.config import Config
    import sqlalchemy
    config = Config()
    monkeypatch.setattr(context, 'config', config, raising=False)
    monkeypatch.setenv('DATABASE_URL', FAKE_URL)
    monkeypatch.setattr(context, 'is_offline_mode', lambda: offline)
    configure = MagicMock()
    migrate = MagicMock()
    monkeypatch.setattr(context, 'configure', configure)
    monkeypatch.setattr(context, 'run_migrations', migrate)
    monkeypatch.setattr(context, 'begin_transaction', MagicMock())
    engine = MagicMock()
    create = MagicMock(return_value=engine)
    monkeypatch.setattr(sqlalchemy, 'create_engine', create)
    runpy.run_path(str(ROOT / 'alembic/env.py'))
    assert config.get_main_option('sqlalchemy.url') is None
    migrate.assert_called_once()
    if offline:
        assert configure.call_args.kwargs['url'] == FAKE_URL
        create.assert_not_called()
    else:
        assert create.call_args.args == (FAKE_URL,)
        assert create.call_args.kwargs['hide_parameters'] is True
        engine.dispose.assert_called_once()


def test_alembic_cli_falha_sem_url_ou_senha():
    env = dict(os.environ, DATABASE_URL=FAKE_URL, SECRET_KEY='ficticio', PYTHON_DOTENV_DISABLED='1')
    # Falha antes de qualquer conexão: dialect deliberadamente inválido.
    env['DATABASE_URL'] = FAKE_URL.replace('postgresql+psycopg2', 'dialeto_inexistente')
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', 'current'], cwd=ROOT,
        env=env, capture_output=True, timeout=15,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert FAKE_URL.encode() not in output
    assert b'segredo-ficticio' not in output
    assert b'RuntimeError' in output


def test_entrada_servico_falha_sem_traceback_sensivel():
    code = '''import runpy,uvicorn
def fail(*a,**k):raise ValueError("postgresql://operador:valor-sintetico@localhost/db")
uvicorn.run=fail
runpy.run_module("app",run_name="__main__")
'''
    result = subprocess.run(
        [sys.executable, '-c', code], cwd=ROOT,
        env=dict(os.environ, PYTHON_DOTENV_DISABLED='1'),
        capture_output=True, timeout=15,
    )
    assert result.returncode == 1
    assert b'valor-sintetico' not in result.stdout + result.stderr
    assert b'postgresql' not in result.stdout + result.stderr
    assert b'ValueError' in result.stderr


def test_erro_na_finalizacao_nao_imprime_excecao():
    code = '''from app.core.logging import install_safe_logging
install_safe_logging()
class ObjectWithFailure:
 def __del__(self):raise ValueError("postgresql://operador:valor-sintetico@localhost/db")
x=ObjectWithFailure()
del x
'''
    result = subprocess.run(
        [sys.executable, '-c', code], cwd=ROOT,
        env=dict(os.environ, PYTHON_DOTENV_DISABLED='1'),
        capture_output=True, timeout=15,
    )
    assert result.returncode == 0
    assert b'valor-sintetico' not in result.stdout + result.stderr
    assert b'postgresql' not in result.stdout + result.stderr
    assert b'ValueError' in result.stderr
