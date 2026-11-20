"""Testes de roteamento e cookies executados dentro da imagem, com persistência simulada."""
import asyncio
import json
import os
import re
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from sqlalchemy.exc import OperationalError

from app.api.routes import auth, portal_clientes
from app.db.database import get_db
from app.main import app


def chamar(path, method='GET', body='', **headers):
    async def executar():
        mensagens = []

        async def receive():
            return {'type': 'http.request', 'body': body.encode(), 'more_body': False}

        async def send(message):
            mensagens.append(message)

        await app({
            'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.4'},
            'http_version': '1.1', 'scheme': 'https', 'method': method,
            'path': path, 'raw_path': path.encode(), 'query_string': b'', 'root_path': '',
            'server': ('fixture.example.test', 443), 'client': ('127.0.0.1', 1234),
            'headers': [(k.lower().replace('_', '-').encode(), v.encode()) for k, v in headers.items()],
        }, receive, send)
        inicio = mensagens[0]
        return inicio['status'], dict(inicio['headers']), b''.join(m.get('body', b'') for m in mensagens[1:])
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
        self.assertEqual(chamar('/openapi.json')[0], 200)
        _, cab, _ = chamar('/health', origin='https://fixture.example.test')
        self.assertIn(b'ETag', cab[b'access-control-expose-headers'])

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

    def test_login_logout_da_equipe(self):
        usuario = SimpleNamespace(id=uuid4(), nome='Admin teste', email='admin@example.com', telefone=None,
                                  perfil='admin', ativo=True, data_cadastro=datetime.now(timezone.utc), senha_hash='fixture')
        db = MagicMock()
        db.scalar.return_value = usuario
        app.dependency_overrides[get_db] = lambda: db
        self.addCleanup(app.dependency_overrides.clear)
        sessoes = set()

        def emitir(*_):
            sessoes.add('sessao-equipe')
            return 'sessao-equipe'

        with (patch.object(auth, 'verificar_senha', return_value=True),
              patch.object(auth.sessoes_equipe, 'emitir', side_effect=emitir),
              patch.object(auth.sessoes_equipe, 'validar', side_effect=lambda _, t: usuario if t in sessoes else None),
              patch.object(auth.sessoes_equipe, 'revogar', side_effect=lambda _, t, __: sessoes.discard(t))):
            status, _, corpo = chamar('/auth/login', 'POST', 'username=admin%40example.com&password=fixture',
                                      content_type='application/x-www-form-urlencoded')
            self.assertEqual(status, 200)
            token = 'Bearer ' + json.loads(corpo)['access_token']
            self.assertEqual(chamar('/auth/me', authorization=token)[0], 200)
            self.assertEqual(chamar('/auth/logout', 'POST', authorization=token)[0], 204)
            self.assertEqual(chamar('/auth/me', authorization=token)[0], 401)


if __name__ == '__main__':
    unittest.main()
