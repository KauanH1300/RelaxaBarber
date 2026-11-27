"""Homologação HTTP da etapa 4 no Supabase de TESTES, com entrega capturada em memória."""
import json
import logging
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from http.cookiejar import Cookie, CookieJar, DefaultCookiePolicy
from threading import Thread
from time import sleep
from unittest.mock import patch
from urllib import error, parse, request
from uuid import uuid4

import uvicorn
from sqlalchemy import create_engine, delete, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ORIGEM = 'http://127.0.0.1:5173'


class Cookies(CookieJar):
    def get(self, nome):
        return next((c.value for c in self if c.name == nome), None)

    def set(self, nome, valor):
        self.set_cookie(Cookie(0, nome, valor, None, False, '127.0.0.1', False, False,
                               '/', True, False, None, True, None, None, {}))


class Resposta:
    def __init__(self, resposta):
        with resposta:
            self.status_code = resposta.code
            self.headers = resposta.headers
            self.body = resposta.read()

    def json(self):
        return json.loads(self.body)


class Navegador:
    def __init__(self, ip):
        self.ip = ip
        self.cookies = Cookies(policy=DefaultCookiePolicy(secure_protocols=('http', 'https')))
        self.opener = request.build_opener(request.ProxyHandler({}), request.HTTPCookieProcessor(self.cookies))

    def request(self, method, path, *, headers=None, data=None, json=None):
        cabecalhos = {'X-Forwarded-For': self.ip, **(headers or {})}
        if data is not None:
            cabecalhos['Content-Type'] = 'application/x-www-form-urlencoded'
            data = parse.urlencode(data).encode()
        if json is not None:
            cabecalhos['Content-Type'] = 'application/json'
            data = json_bytes(json)
        req = request.Request('http://127.0.0.1:8000' + path, headers=cabecalhos, data=data, method=method)
        try:
            return Resposta(self.opener.open(req, timeout=30))
        except error.HTTPError as resposta:
            return Resposta(resposta)

    def get(self, path, **kwargs):
        return self.request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self.request('POST', path, **kwargs)


def json_bytes(payload):
    return json.dumps(payload).encode()

def homologar():
    url = make_url(os.environ['DATABASE_URL'])
    projeto = url.host.split('.')[1] if url.host.startswith('db.') else (url.username or '').split('.')[-1]
    assert url.host.endswith(('.supabase.co', '.supabase.com')) and projeto == 'olboimgffwxccxsocawb'
    os.environ['BACKEND_CORS_ORIGINS'] = '["' + ORIGEM + '"]'
    from app.core import cookies_equipe as cookies
    from app.core.security import hash_senha
    from app.db.database import get_db
    from app.main import app
    from app.models.cliente import Cliente
    from app.models.portal_cliente import ContaPortalCliente, LimitePortalCliente, SessaoPortalCliente
    from app.models.sessao_equipe import DispositivoEquipe, RecuperacaoEquipe
    from app.models.usuario import Usuario, PerfilEnum
    from app.services import entrega_codigo_cliente as smtp, sessoes_equipe
    from app.services.portal_cliente import agora, segredo

    owner = create_engine(url, hide_parameters=True)
    def sessao():
        with Session(owner, autoflush=False) as db:
            yield db

    marca = uuid4()
    perfis = {nome: PerfilEnum.ADMIN for nome in ('fluxo', 'expira', 'limite', 'falha', 'mudanca')}
    perfis.update({perfil.value: perfil for perfil in PerfilEnum if perfil != PerfilEnum.ADMIN})
    ids = {nome: uuid4() for nome in perfis}
    emails = {nome: f'qa-{nome}-{marca.hex}@example.com' for nome in perfis}
    cliente_id, cliente_email = uuid4(), f'qa-cliente-{marca.hex}@example.com'
    email_novo = f'qa-novo-{marca.hex}@example.com'
    senha, senha_nova = ('Qa!9' + secrets.token_urlsafe(22) for _ in range(2))
    rede = f'198.18.{marca.bytes[0]}.'
    ips = {nome: rede + str(i) for i, nome in enumerate(perfis, 10)}
    codigos = {}

    def capturar(email, codigo):
        assert email in set(emails.values()) | {email_novo}
        codigos[email] = codigo

    def abrir(nome, confiavel=None):
        navegador = Navegador(ips[nome])
        if confiavel:
            navegador.cookies.set(cookies.DISPOSITIVO, confiavel)
        return navegador

    def escrita(navegador, path, *, metodo='POST', status=200, **kwargs):
        bootstrap = navegador.post('/auth/csrf', headers={'Origin': ORIGEM})
        assert bootstrap.status_code == 200
        resposta = navegador.request(metodo, path, headers={
            'Origin': ORIGEM, 'X-Equipe-CSRF': bootstrap.json()['csrf'],
        }, **kwargs)
        if resposta.status_code != status:
            print(f'HTTP {metodo} {path}: {resposta.status_code}, esperado {status}.', flush=True)
            raise AssertionError('Resposta HTTP inesperada')
        return resposta

    def login(navegador, nome, status=202, password=senha):
        return escrita(navegador, '/auth/login', status=status,
                       data={'username': emails[nome], 'password': password})

    def verificar(navegador, codigo, *, confiar=False, status=200):
        return escrita(navegador, '/auth/login/email/verificar', status=status,
                       json={'codigo': codigo, 'confiar': confiar})

    def avancar_reenvio(nome):
        chave = segredo('limite', f'equipe:login-admin:envio:usuario:{ids[nome]}')
        with Session(owner) as db, db.begin():
            db.execute(update(LimitePortalCliente).where(LimitePortalCliente.chave == chave)
                       .values(ultimo=agora() - timedelta(seconds=61)))

    def novo_confiavel(nome, password=senha):
        navegador = abrir(nome)
        login(navegador, nome, password=password)
        verificar(navegador, codigos[emails[nome]], confiar=True)
        return navegador, navegador.cookies.get(cookies.DISPOSITIVO)

    def dispositivos(navegador):
        resposta = navegador.get('/auth/dispositivos-confiaveis')
        assert resposta.status_code == 200
        return resposta.json()

    with Session(owner) as db, db.begin():
        assert db.scalar(text('select version_num from public.alembic_version')) == '5ce84d69be21'
        for coluna in ('codigo_hash', 'expira_em', 'login_enviado_em'):
            assert db.scalar(text("select has_column_privilege('relaxabarber_runtime', "
                                  "'public.equipe_recuperacoes', :coluna, 'UPDATE')"), {'coluna': coluna})
        for permissao in ('SELECT', 'INSERT', 'DELETE'):
            assert db.scalar(text("select has_table_privilege('relaxabarber_runtime', "
                                  "'public.equipe_dispositivos_confiaveis', :permissao)"), {'permissao': permissao})
        senha_hash = hash_senha(senha)
        db.add_all([
            Usuario(id=ids[nome], nome=f'QA etapa 4 {nome}', email=emails[nome], perfil=perfil,
                    senha_hash=senha_hash, email_confirmado_em=None if nome == 'fluxo' else agora())
            for nome, perfil in perfis.items()
        ])
        telefone = str(11900000000 + int.from_bytes(marca.bytes[:4], 'big') % 100000000)
        db.add(Cliente(id=cliente_id, nome='QA etapa 4 cliente', email=cliente_email,
                       telefone=telefone, senha_hash=senha_hash, conta_ativada=True))
        db.flush()
        db.add(ContaPortalCliente(cliente_id=cliente_id, email_confirmado=cliente_email))
        legado = sessoes_equipe.emitir(db, ids['fluxo'])

    app.dependency_overrides[get_db] = sessao
    servidor = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8000,
                                              log_level='error', lifespan='off',
                                              forwarded_allow_ips='127.0.0.1'))
    thread = Thread(target=servidor.run, daemon=True)
    try:
        thread.start()
        for _ in range(100):
            if servidor.started:
                break
            sleep(.05)
        assert servidor.started
        with patch.object(smtp, 'enviar', side_effect=capturar):
            navegador = abrir('fluxo')
            resposta = login(navegador, 'fluxo')
            assert resposta.json() == {'verificacao_email': True, 'validade_segundos': 300, 'reenvio_segundos': 60}
            cabecalhos = resposta.headers.get_all('set-cookie')
            assert any(cookies.PENDENTE in c and 'HttpOnly' in c
                       and ('Secure' in c) == cookies.SECURE for c in cabecalhos)
            assert navegador.cookies.get(cookies.COOKIE) is None
            for rota in ('/auth/me', '/usuarios', '/auth/dispositivos-confiaveis'):
                assert navegador.get(rota).status_code == 401
            assert abrir('fluxo').get('/usuarios', headers={'Cookie': f'{cookies.COOKIE}={legado}'}).status_code == 401
            assert navegador.post('/auth/login/email/verificar', json={'codigo': codigos[emails['fluxo']]}).status_code == 403
            escrita(navegador, '/auth/login/email/reenviar', status=429)
            inicial = codigos[emails['fluxo']]
            avancar_reenvio('fluxo')
            escrita(navegador, '/auth/login/email/reenviar')
            atual = codigos[emails['fluxo']]
            assert inicial != atual
            verificar(navegador, inicial, status=400)

            pendente = navegador.cookies.get(cookies.PENDENTE)
            def consumir():
                paralelo = abrir('fluxo')
                paralelo.cookies.set(cookies.PENDENTE, pendente)
                csrf = paralelo.post('/auth/csrf', headers={'Origin': ORIGEM}).json()['csrf']
                resposta = paralelo.post('/auth/login/email/verificar', json={'codigo': atual, 'confiar': True},
                                         headers={'Origin': ORIGEM, 'X-Equipe-CSRF': csrf})
                return resposta.status_code, paralelo, resposta
            with ThreadPoolExecutor(2) as pool:
                resultados = list(pool.map(lambda _: consumir(), range(2)))
            assert sorted(r[0] for r in resultados) == [200, 400]
            _, navegador, resposta = next(r for r in resultados if r[0] == 200)
            assert navegador.get('/auth/me').json()['email_confirmado_em']
            assert navegador.get(f'/usuarios/cadastros/{uuid4()}').status_code == 404
            assert any(cookies.DISPOSITIVO in c and 'HttpOnly' in c and 'Max-Age=2592000' in c
                       for c in resposta.headers.get_all('set-cookie'))
            confiavel = navegador.cookies.get(cookies.DISPOSITIVO)
            original = dispositivos(navegador)[0]
            assert original['atual']
            with Session(owner) as db:
                dispositivo = db.scalar(select(DispositivoEquipe).where(DispositivoEquipe.usuario_id == ids['fluxo']))
                assert dispositivo.token_hash == segredo('equipe-dispositivo', confiavel)
                assert dispositivo.expira_em - dispositivo.criado_em == timedelta(days=30)
            escrita(navegador, '/auth/logout', status=204)
            assert navegador.cookies.get(cookies.DISPOSITIVO) == confiavel
            assert all(cookies.DISPOSITIVO not in c for c in login(navegador, 'fluxo', 200).headers.get_all('set-cookie'))
            assert dispositivos(navegador)[0] == original
            avancar_reenvio('fluxo')
            outro, outro_token = novo_confiavel('fluxo')
            assert len(dispositivos(outro)) == 2
            escrita(outro, '/auth/dispositivos-confiaveis/' + original['id'], metodo='DELETE', status=204)
            assert len(dispositivos(outro)) == 1
            avancar_reenvio('fluxo')
            revogado = abrir('fluxo', confiavel)
            login(revogado, 'fluxo')
            verificar(revogado, codigos[emails['fluxo']])
            assert not dispositivos(revogado)[0]['atual']
            escrita(outro, '/auth/dispositivos-confiaveis', metodo='DELETE', status=204)
            assert not dispositivos(outro) and not outro.cookies.get(cookies.DISPOSITIVO)
            avancar_reenvio('fluxo')
            login(abrir('fluxo', outro_token), 'fluxo')
            print('OK: confirmação inicial, API direta, CSRF, reenvio, corrida, confiança e revogações.', flush=True)

            n = abrir('expira')
            login(n, 'expira')
            with Session(owner) as db, db.begin():
                db.execute(update(RecuperacaoEquipe).where(RecuperacaoEquipe.usuario_id == ids['expira'])
                           .values(expira_em=agora() - timedelta(seconds=1)))
            verificar(n, codigos[emails['expira']], status=400)
            avancar_reenvio('expira')
            escrita(n, '/auth/login/email/reenviar')
            verificar(n, codigos[emails['expira']], confiar=True)
            token_expirado = n.cookies.get(cookies.DISPOSITIVO)
            with Session(owner) as db, db.begin():
                db.execute(update(DispositivoEquipe).where(DispositivoEquipe.usuario_id == ids['expira'])
                           .values(expira_em=agora() - timedelta(seconds=1)))
            assert not dispositivos(n)
            avancar_reenvio('expira')
            n = abrir('expira', token_expirado)
            login(n, 'expira')
            with Session(owner) as db, db.begin():
                db.execute(update(RecuperacaoEquipe).where(RecuperacaoEquipe.usuario_id == ids['expira'])
                           .values(login_ate=agora() - timedelta(seconds=1)))
            verificar(n, codigos[emails['expira']], status=400)
            print('OK: expiração do código, do desafio e do dispositivo.', flush=True)

            n = abrir('limite')
            login(n, 'limite')
            certo = codigos[emails['limite']]
            errado = '111111' if certo != '111111' else '222222'
            for _ in range(5):
                verificar(n, errado, status=400)
            verificar(n, certo, status=400)
            with patch.object(smtp, 'enviar', side_effect=smtp.EntregaIndisponivel):
                n = abrir('falha')
                login(n, 'falha', 503)
                assert n.cookies.get(cookies.PENDENTE) is None and n.get('/usuarios').status_code == 401
            print('OK: cinco tentativas e falha de SMTP fechada.', flush=True)

            n, token = novo_confiavel('mudanca')
            codigos.pop(emails['mudanca'])
            recuperacao = escrita(abrir('mudanca'), '/auth/recuperar', status=202, json={'email': emails['mudanca']}).json()
            for _ in range(100):
                if emails['mudanca'] in codigos:
                    break
                sleep(.05)
            assert emails['mudanca'] in codigos
            escrita(abrir('mudanca'), '/auth/redefinir', status=204, json={
                'solicitacao_id': recuperacao['solicitacao_id'], 'codigo': codigos[emails['mudanca']], 'senha': senha_nova,
            })
            assert n.get('/auth/me').status_code == 401
            avancar_reenvio('mudanca')
            n = abrir('mudanca', token)
            login(n, 'mudanca', password=senha_nova)
            verificar(n, codigos[emails['mudanca']], confiar=True)
            token = n.cookies.get(cookies.DISPOSITIVO)
            escrita(n, '/auth/trocar-senha', status=204, json={'senha_atual': senha_nova, 'senha': senha})
            assert not n.cookies.get(cookies.DISPOSITIVO)
            avancar_reenvio('mudanca')
            n = abrir('mudanca', token)
            login(n, 'mudanca')
            verificar(n, codigos[emails['mudanca']], confiar=True)
            token = n.cookies.get(cookies.DISPOSITIVO)
            escrita(n, '/usuarios/' + str(ids['mudanca']), metodo='PATCH',
                    json={'nome': 'QA renomeado', 'email': email_novo, 'perfil': 'admin', 'ativo': True})
            assert n.get('/auth/me').status_code == 401
            avancar_reenvio('mudanca')
            emails['mudanca'] = email_novo
            n = abrir('mudanca', token)
            login(n, 'mudanca')
            verificar(n, codigos[email_novo], confiar=True)
            token_novo = n.cookies.get(cookies.DISPOSITIVO)
            assert len(dispositivos(n)) == 1 and token_novo != token
            rota = '/usuarios/' + str(ids['mudanca'])
            cadastro = {'nome': 'QA renomeado', 'email': email_novo, 'ativo': True}
            escrita(outro, rota, metodo='PATCH', json={**cadastro, 'perfil': 'recepcao'})
            assert n.get('/auth/me').status_code == 401
            recepcao = abrir('mudanca')
            login(recepcao, 'mudanca', 200)
            escrita(outro, rota, metodo='PATCH', json={**cadastro, 'perfil': 'admin'})
            assert recepcao.get('/auth/me').status_code == 401
            avancar_reenvio('mudanca')
            login(abrir('mudanca', token_novo), 'mudanca')
            print('OK: recuperação e mudanças de senha, e-mail e perfil invalidam a confiança.', flush=True)

            for nome in (p.value for p in PerfilEnum if p != PerfilEnum.ADMIN):
                n = abrir(nome)
                login(n, nome, 200)
                assert n.get('/auth/me').json()['perfil'] == nome and not n.cookies.get(cookies.PENDENTE)
                assert n.get('/auth/dispositivos-confiaveis').status_code == 403
            cliente = abrir('recepcao')
            resposta = cliente.post('/portal-clientes/login', headers={'Origin': ORIGEM},
                                    json={'email': cliente_email, 'senha': senha})
            assert resposta.status_code == 200 and cliente.get('/portal-clientes/me').status_code == 200
            assert cliente.get('/auth/me').status_code == 401 and cliente_email not in codigos
            print('OK: demais perfis e portal do cliente mantêm seus fluxos.', flush=True)
    finally:
        servidor.should_exit = True
        thread.join(timeout=5)
        app.dependency_overrides.pop(get_db, None)
        with Session(owner) as db, db.begin():
            db.execute(delete(SessaoPortalCliente).where(SessaoPortalCliente.cliente_id == cliente_id))
            db.execute(delete(ContaPortalCliente).where(ContaPortalCliente.cliente_id == cliente_id))
            db.execute(delete(Cliente).where(Cliente.id == cliente_id))
            db.execute(delete(Usuario).where(Usuario.id.in_(ids.values())))
        owner.dispose()
        print('Contas fictícias removidas.', flush=True)


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    try:
        homologar()
    except AssertionError as exc:
        import traceback
        linha = traceback.extract_tb(exc.__traceback__)[-1].lineno
        print(f'Falha de homologação na linha {linha}.', flush=True)
        raise SystemExit(1) from None
    except Exception as exc:
        import traceback
        local = traceback.extract_tb(exc.__traceback__)[-1]
        print(f'Falha de homologação: {type(exc).__name__} em {local.name}:{local.lineno}.', flush=True)
        raise SystemExit(1) from None
