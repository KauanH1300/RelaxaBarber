import json
import pytest
from sqlalchemy import text
from test_sessoes_equipe import equipe, EMAIL, ANTIGA, NOVA
from test_contexto_filiais import duas_filiais
from test_concorrencia import data
from test_financeiro_http import api
from test_seguranca_horarios import chamar

ORIGIN = 'http://localhost:5173'

def request(api, path, cookie='', csrf='', method='GET', dados=None, origin=ORIGIN, form=False):
    return chamar(api, path, method=method, dados=dados, form=form,
        cabecalhos=[('origin', origin), ('cookie', cookie), ('x-equipe-csrf', csrf)],
        resposta_bruta=True)

def entrar(api):
    from app.core.cookies_equipe import COOKIE
    status, headers, body = request(api, '/auth/csrf', method='POST')
    assert status == 200
    cookie = headers[b'set-cookie'].decode().split(';')[0]
    csrf = json.loads(body)['csrf']
    status, headers, body = request(api, '/auth/login', cookie, csrf, 'POST',
        {'username': EMAIL, 'password': ANTIGA}, form=True)
    assert status == 200, body
    assert 'access_token' not in json.loads(body)
    raw = headers[b'set-cookie'].decode()
    assert 'HttpOnly' in raw and 'Secure' in raw and 'SameSite=lax' in raw
    cookie = raw.split(';')[0]
    assert cookie.startswith(COOKIE+'=')
    csrf = json.loads(request(api, '/auth/csrf', cookie, method='POST')[2])['csrf']
    return cookie, csrf

@pytest.mark.parametrize('perfil', ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_login_permissoes_logout(api, pg, equipe, perfil):
    with pg.begin() as conn:
        conn.execute(text("UPDATE usuarios SET perfil=:p WHERE id=:id"), {'p': perfil.upper(), 'id': equipe['admin']})
    cookie, csrf = entrar(api)
    result = request(api, '/auth/me', cookie)
    assert json.loads(result[2])['perfil'] == perfil
    assert request(api, '/filiais', cookie)[0] == 200
    assert request(api, '/auth/logout', cookie, csrf, 'POST')[0] == 204
    assert request(api, '/auth/me', cookie)[0] == 401

def test_csrf_isolamento_e_revogacao(api, pg, equipe):
    from app.core.cookies_equipe import COOKIE
    from app.core.security import SECRET_KEY, ALGORITHM
    import jwt
    cookie, csrf = entrar(api)
    assert request(api, '/auth/logout', cookie, '', 'POST')[0] == 403
    assert request(api, '/auth/logout', cookie, csrf, 'POST', origin='https://evil.example')[0] == 403
    assert request(api, '/auth/logout', cookie, csrf, 'POST', origin='null')[0] == 403
    assert request(api, '/auth/me', 'rb_cliente_sessao='+cookie.split('=',1)[1])[0] == 401
    assert request(api, '/portal-clientes/me', cookie)[0] == 401
    assert chamar(api, '/auth/me', token=cookie.split('=',1)[1])[0] == 401
    claims = jwt.decode(cookie.split('=',1)[1], SECRET_KEY, algorithms=[ALGORITHM])
    claims.pop('transport')
    old = jwt.encode(claims, SECRET_KEY, algorithm=ALGORITHM)
    assert request(api, '/auth/me', COOKIE+'='+old)[0] == 401
    assert request(api, '/auth/trocar-senha', cookie, csrf, 'POST',
        {'senha_atual': ANTIGA, 'senha': NOVA})[0] == 204
    assert request(api, '/auth/me', cookie)[0] == 401

def test_expiracao(api, pg, equipe):
    cookie, csrf = entrar(api)
    with pg.begin() as conn:
        conn.execute(text("UPDATE equipe_sessoes SET expira_em=now()-interval '1 second'"))
    assert request(api, '/auth/me', cookie)[0] == 401

def test_redefinicao_revoga_cookie(api, pg, equipe, monkeypatch):
    from app.services import entrega_codigo_cliente
    entregues = []
    monkeypatch.setattr(entrega_codigo_cliente, 'enviar', lambda _, codigo: entregues.append(codigo))
    cookie, csrf = entrar(api)
    status, _, body = request(api, '/auth/recuperar', cookie, csrf, 'POST', {'email': EMAIL})
    assert status == 202 and len(entregues) == 1
    payload = {'solicitacao_id': json.loads(body)['solicitacao_id'], 'codigo': entregues[0], 'senha': NOVA}
    assert request(api, '/auth/redefinir', cookie, csrf, 'POST', payload)[0] == 204
    assert request(api, '/auth/me', cookie)[0] == 401
