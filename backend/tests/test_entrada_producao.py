"""Testes de roteamento e cookies executados dentro da imagem, com persistência simulada."""
import asyncio
import json
import os
import re
import ssl
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.exc import OperationalError

from app.api.routes import auth, portal_clientes
from app.core import cookies_equipe
from app.core.ambiente import configuracao_banco, origens_permitidas
from app.core.http_producao import redes_confiaveis
from app.core.logging import sanitize
from app.db.database import get_db
from app.main import app
from app.services import entrega_codigo_cliente as smtp


ORIGEM = 'https://fixture.example.test'


def chamar(path, method='GET', body='', *, scheme='https', client='192.0.2.2',
           propagar=True, **headers):
    async def executar():
        mensagens = []

        async def receive():
            return {'type': 'http.request', 'body': body.encode(), 'more_body': False}

        async def send(message):
            mensagens.append(message)

        headers.setdefault('host', 'fixture.example.test')
        scope = {
            'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
            'http_version': '1.1', 'scheme': scheme, 'method': method,
            'path': path, 'raw_path': path.encode(), 'query_string': b'', 'root_path': '',
            'server': ('fixture.example.test', 443), 'client': (client, 1234),
            'headers': [(k.lower().replace('_', '-').encode(), v.encode()) for k, v in headers.items()],
        }
        try:
            await app(scope, receive, send)
        except Exception:
            if propagar or not mensagens:
                raise
        inicio = mensagens[0]
        cabecalhos = dict(inicio['headers'])
        if b'set-cookie' in cabecalhos:
            cabecalhos[b'set-cookie'] = b'\n'.join(v for k, v in inicio['headers'] if k == b'set-cookie')
        return inicio['status'], cabecalhos, b''.join(m.get('body', b'') for m in mensagens[1:])
    return asyncio.run(executar())


@unittest.skipUnless(os.getenv('FRONTEND_DIST'), 'Execute com o build de produção disponível')
class EntradaProducao(unittest.TestCase):
    def test_spa_estaticos_e_rotas_api(self):
        status, cab, html = chamar('/estoque/fixture/editar', accept='text/html')
        self.assertEqual(status, 200)
        self.assertIn(b'Accept', cab[b'vary'])
        for caminho in ('/', '/clientes', '/cliente/entrar', '/servicos', '/comandas'):
            self.assertEqual(chamar(caminho, accept='text/html')[2], html)
        self.assertEqual(chamar('/clientes', accept='application/json')[0], 401)
        self.assertEqual(chamar('/clientes', accept='text/html;q=0, application/json')[0], 401)
        self.assertEqual(chamar('/portal-clientes/inexistente', accept='text/html')[0], 404)
        self.assertEqual(chamar('/assets/inexistente.js')[0], 404)
        js = re.search(rb'src="(/assets/[^"]+\.js)"', html).group(1).decode()
        self.assertEqual(chamar(js)[0], 200)
        for caminho in ('/docs', '/redoc', '/openapi.json'):
            self.assertEqual(chamar(caminho)[0], 404)
        _, cab, _ = chamar('/health', origin=ORIGEM)
        self.assertIn(b'ETag', cab[b'access-control-expose-headers'])
        self.assertEqual(cab[b'strict-transport-security'], b'max-age=31536000')
        self.assertEqual(cab[b'x-content-type-options'], b'nosniff')
        self.assertEqual(cab[b'x-frame-options'], b'DENY')
        self.assertEqual(cab[b'referrer-policy'], b'strict-origin-when-cross-origin')
        for parte in (b"frame-ancestors 'none'", b"script-src 'self'", b'fonts.googleapis.com',
                      b'fonts.gstatic.com', b'maps.google.com', b'storage.fixture.test'):
            self.assertIn(parte, cab[b'content-security-policy'])

    def test_https_proxy_e_ip_entregue_ao_rate_limiting(self):
        hostiles = {'scheme': 'http', 'x_forwarded_proto': 'https', 'x_forwarded_for': '198.51.100.99'}
        status, cab, _ = chamar('/auth/csrf', 'POST', origin=ORIGEM, **hostiles)
        self.assertEqual(status, 400)
        self.assertNotIn(b'strict-transport-security', cab)
        self.assertEqual(chamar('/health', scheme='http', client='10.10.0.3', host='10.10.0.1')[0], 200)
        self.assertEqual(chamar('/health', scheme='http')[0], 400)
        self.assertEqual(chamar('/health', host='falso.example.test')[0], 400)

        db = MagicMock()
        db.scalar.return_value = None
        app.dependency_overrides[get_db] = lambda: db
        self.addCleanup(app.dependency_overrides.clear)
        with (patch.object(auth, 'admitir') as admitir, patch.object(auth, 'hash_ficticio', return_value='ficticio'),
              patch.object(auth, 'autenticar_senha', return_value=(False, None))):
            dados = 'username=ficticio%40example.com&password=ficticia'
            origem = {'origin': ORIGEM, 'content_type': 'application/x-www-form-urlencoded',
                      'cookie': cookies_equipe.ANON + '=fixture', 'x_equipe_csrf': cookies_equipe.assinar('fixture')}
            salto = dict(scheme='http', client='::ffff:10.10.0.3', x_forwarded_proto='https',
                         x_forwarded_for='198.51.100.99, 203.0.113.5, 10.11.0.4')
            self.assertEqual(chamar('/auth/login', 'POST', dados, **origem, **salto)[0], 401)
            self.assertEqual(admitir.call_args.args[2], '203.0.113.5')
            self.assertEqual(chamar('/auth/login', 'POST', dados, x_forwarded_for='198.51.100.99', **origem)[0], 401)
            self.assertEqual(admitir.call_args.args[2], '192.0.2.2')
            self.assertEqual(chamar('/auth/login', 'POST', dados, **origem,
                                    **(salto | {'x_forwarded_proto': 'https,http'}))[0], 400)

    def test_cors_csrf_e_erros_privados(self):
        headers = dict(access_control_request_method='PATCH',
                       access_control_request_headers='content-type,x-equipe-csrf,idempotency-key')
        status, cab, _ = chamar('/auth/login', 'OPTIONS', origin=ORIGEM, **headers)
        self.assertEqual(status, 200)
        self.assertEqual(cab[b'access-control-allow-origin'].decode(), ORIGEM)
        self.assertEqual(chamar('/auth/login', 'OPTIONS', origin='https://falso.example.test', **headers)[0], 400)
        headers['access_control_request_headers'] = 'x-cabecalho-nao-autorizado'
        self.assertEqual(chamar('/auth/login', 'OPTIONS', origin=ORIGEM, **headers)[0], 400)
        self.assertEqual(chamar('/auth/csrf', 'POST', origin='null')[0], 403)
        self.assertEqual(chamar('/auth/login/email/verificar', 'POST', '{"codigo":"123456"}',
                                content_type='application/json', origin=ORIGEM)[0], 403)
        with patch('app.main.engine') as engine:
            engine.connect.side_effect = RuntimeError('detalhe privado')
            status, cab, corpo = chamar('/ready', propagar=False)
        self.assertEqual(status, 500)
        self.assertNotIn(b'detalhe privado', corpo)
        self.assertEqual(cab[b'cache-control'], b'no-store')
        self.assertIn(b'content-security-policy', cab)
        _, _, corpo = chamar('/portal-clientes/login', 'POST', '{"email":"valor-privado","senha":"X"}',
                             content_type='application/json', origin=ORIGEM)
        self.assertNotIn(b'valor-privado', corpo)

    def test_configuracoes_fortes_e_starttls(self):
        _, opcoes = configuracao_banco('postgresql+psycopg2:///?service=relaxabarber_runtime')
        self.assertEqual(opcoes['connect_args'], {'sslmode': 'verify-full', 'gssencmode': 'disable'})
        with self.assertRaises(RuntimeError):
            configuracao_banco('postgresql+psycopg2://fixture.invalid/db?sslmode=require')
        with patch.dict(os.environ, {'BACKEND_TRUSTED_PROXY_CIDRS': '0.0.0.0/0'}):
            with self.assertRaises(RuntimeError):
                redes_confiaveis()
        with patch.dict(os.environ, {'BACKEND_CORS_ORIGINS': '["http://fixture.example.test"]'}):
            with self.assertRaises(RuntimeError):
                origens_permitidas()
        with patch.dict(os.environ, {'SUPABASE_SERVICE_ROLE_KEY': 'token-fixture-storage'}):
            self.assertNotIn('token-fixture-storage', sanitize('info token-fixture-storage'))
        with (patch.object(smtp, 'configuracao', return_value=('smtp.example.test', 2525,
                'origem@example.com', 'starttls', 'ficticio', 'ficticia')),
              patch.object(smtp.smtplib, 'SMTP') as conexao):
            cliente = conexao.return_value.__enter__.return_value
            cliente.send_message.return_value = {}
            smtp.enviar('destino@example.com', '123456')
            self.assertEqual([chamada[0] for chamada in cliente.method_calls],
                             ['ehlo', 'starttls', 'ehlo', 'login', 'send_message'])
            contexto = cliente.starttls.call_args.kwargs['context']
            self.assertEqual(contexto.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(contexto.check_hostname)

    def test_prontidao_e_disponibilidade_independentes(self):
        with patch('app.main.engine') as engine:
            self.assertEqual(chamar('/ready')[0], 200)
            engine.connect.side_effect = OperationalError(None, None, Exception('detalhe privado'))
            status, cab, corpo = chamar('/ready')
            self.assertEqual(status, 503)
            self.assertEqual(cab[b'cache-control'], b'no-store')
            self.assertNotIn(b'detalhe privado', corpo)
            self.assertEqual(chamar('/health')[0], 200)

    def test_login_logout_e_cookie_do_portal(self):
        cliente = dict(id=uuid4(), nome='Cliente teste', email='cliente@example.com', telefone='81999999999')
        corpo = json.dumps({'email': cliente['email'], 'senha': 'fixture'})
        origem = {'origin': 'https://fixture.example.test', 'content_type': 'application/json'}
        sessoes = set()

        def login(*_):
            sessoes.add('sessao-portal')
            return 'sessao-portal'

        def autenticar(_, token):
            if token not in sessoes:
                raise portal_clientes.portal.PortalFalha(401, 'Sessão encerrada')
            return cliente

        app.dependency_overrides[get_db] = lambda: None
        self.addCleanup(app.dependency_overrides.clear)
        with (patch.object(portal_clientes.portal, 'login', side_effect=login),
              patch.object(portal_clientes.portal, 'autenticar', side_effect=autenticar),
              patch.object(portal_clientes.portal, 'logout', side_effect=lambda _, token: sessoes.discard(token))):
            self.assertEqual(chamar('/portal-clientes/login', 'POST', corpo, **(origem | {'origin': 'https://outra.example.test'}))[0], 403)
            with patch.dict(os.environ, {'CLIENT_PORTAL_COOKIE_SECURE': 'false'}):
                status, cab, _ = chamar('/portal-clientes/login', 'POST', corpo, **origem)
            self.assertEqual(status, 200)
            cookie = cab[b'set-cookie'].decode()
            for atributo in ('HttpOnly', 'Secure', 'SameSite=strict', 'Path=/portal-clientes'):
                self.assertIn(atributo.lower(), cookie.lower())
            credencial = cookie.split(';', 1)[0]
            self.assertEqual(chamar('/portal-clientes/me', cookie=credencial)[0], 200)
            status, cab, _ = chamar('/portal-clientes/logout', 'POST', cookie=credencial, **origem)
            self.assertEqual(status, 204)
            self.assertIn(b'Max-Age=0', cab[b'set-cookie'])
            self.assertIn(b'Path=/portal-clientes', cab[b'set-cookie'])
            self.assertEqual(chamar('/portal-clientes/me', cookie=credencial)[0], 401)

    def test_cookies_de_sessao_e_dispositivo_no_https_publicado(self):
        app.dependency_overrides[get_db] = lambda: None
        self.addCleanup(app.dependency_overrides.clear)
        with patch.object(auth.login_admin, 'verificar', return_value=(200, 'ficticia', 'dispositivo-ficticio')):
            status, cab, _ = chamar('/auth/login/email/verificar', 'POST', '{"codigo":"012345","confiar":true}',
                                    origin=ORIGEM, content_type='application/json',
                                    cookie=cookies_equipe.PENDENTE + '=fixture',
                                    x_equipe_csrf=cookies_equipe.assinar('fixture'))
        self.assertEqual(status, 200)
        for nome in (b'__Host-rb_equipe_sessao=', b'__Host-rb_equipe_dispositivo='):
            cookie = next(linha for linha in cab[b'set-cookie'].splitlines() if linha.startswith(nome))
            for parte in (b'HttpOnly', b'Secure', b'SameSite=lax', b'Path=/'):
                self.assertIn(parte, cookie)
        self.assertIn(b'Max-Age=2592000', cookie)
        self.assertEqual(cab[b'cache-control'], b'no-store')


if __name__ == '__main__':
    unittest.main()
