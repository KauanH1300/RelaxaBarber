"""Políticas de configuração compartilhadas entre a API e as migrações."""
import json
import os
import re
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

load_dotenv()

ORIGENS_LOCAIS = '["http://localhost:5173","http://127.0.0.1:5173"]'


def producao():
    return os.getenv('ENV', 'production').lower() not in {'development', 'test'}


def origem_http(valor, *, somente_https):
    if not isinstance(valor, str) or not re.fullmatch(
        r'https?://(?:[a-z0-9.-]+|\[[a-f0-9:]+\])(?::[0-9]{1,5})?', valor,
    ):
        raise ValueError
    url = urlsplit(valor)
    if (somente_https and url.scheme != 'https') or url.port == 0:
        raise ValueError
    return valor


def origens_permitidas():
    publicada = producao()
    try:
        origens = json.loads(os.getenv('BACKEND_CORS_ORIGINS', '[]' if publicada else ORIGENS_LOCAIS))
        if not isinstance(origens, list) or (publicada and not origens):
            raise ValueError
        return list(dict.fromkeys(origem_http(x, somente_https=publicada) for x in origens))
    except (TypeError, ValueError):
        raise RuntimeError('BACKEND_CORS_ORIGINS deve conter origens exatas válidas') from None


def configuracao_banco(valor):
    url = make_url(valor)
    opcoes = {'hide_parameters': True}
    if producao():
        if url.drivername not in {'postgresql', 'postgresql+psycopg2'}:
            raise RuntimeError('Produção exige PostgreSQL com TLS autenticado')
        if url.query.get('sslmode', 'verify-full') != 'verify-full':
            raise RuntimeError('Produção exige sslmode=verify-full')
        # Também se aplica a perfis libpq e valores PGSSLMODE/PGGSSENCMODE.
        opcoes['connect_args'] = {'sslmode': 'verify-full', 'gssencmode': 'disable'}
    return url, opcoes


def exigir_tls_postgres(engine):
    if producao():
        @event.listens_for(engine, 'do_connect')
        def conectar_com_tls(dialeto, registro, args, parametros):
            conexao = dialeto.connect(*args, **parametros)
            if not conexao.info.ssl_in_use:
                conexao.close()
                raise OperationalError(None, None, RuntimeError('PostgreSQL sem TLS'))
            return conexao


def chave_assinatura():
    chave = os.environ['SECRET_KEY']
    if producao() and (len(chave.encode()) < 32 or chave.startswith('troque-por-')):
        raise RuntimeError('SECRET_KEY de produção precisa ser forte e exclusiva')
    return chave
