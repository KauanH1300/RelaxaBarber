"""Validação do destino não abre conexões."""
import pytest
from conftest import validated_url


@pytest.mark.parametrize('url', [
    'postgresql+psycopg2://rb_concorrencia_test:x@db.example.supabase.co:55432/relaxabarber_concorrencia_test',
    'postgresql+psycopg2://rb_concorrencia_test:x@127.0.0.1:5432/relaxabarber_concorrencia_test',
    'postgresql+psycopg2://rb_concorrencia_test:x@127.0.0.1:55432/postgres',
    'postgresql+psycopg2://postgres:x@127.0.0.1:55432/relaxabarber_concorrencia_test',
    'postgresql+psycopg2://rb_concorrencia_test:x@127.0.0.1:55432/relaxabarber_concorrencia_test?host=externo',
])
def test_destinos_recusados(monkeypatch, url):
    monkeypatch.setenv('RELAXABARBER_TEST_DATABASE_URL', url)
    with pytest.raises(pytest.UsageError):
        validated_url()


def test_database_url_da_aplicacao_recusada(monkeypatch):
    url = 'postgresql+psycopg2://rb_concorrencia_test:x@127.0.0.1:55432/relaxabarber_concorrencia_test'
    monkeypatch.setenv('RELAXABARBER_TEST_DATABASE_URL', url)
    monkeypatch.setenv('DATABASE_URL', url)
    with pytest.raises(pytest.UsageError):
        validated_url()
