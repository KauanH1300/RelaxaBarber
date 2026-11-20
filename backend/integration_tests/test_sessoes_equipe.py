"""Fluxos HTTP da equipe no PostgreSQL descartável com ACL real."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from test_concorrencia import data
from test_contexto_filiais import duas_filiais
from test_financeiro_http import api
from test_seguranca_horarios import chamar

EMAIL = 'equipe@example.com'
ANTIGA = 'senha antiga da fixture'
NOVA = 'senha nova da fixture'


@pytest.fixture
def equipe(pg, duas_filiais):
    from app.core.security import hash_senha
    from app.models import Usuario

    with Session(pg) as db, db.begin():
        usuario = db.get(Usuario, duas_filiais['admin'])
        usuario.email, usuario.senha_hash = EMAIL, hash_senha(ANTIGA)
    return duas_filiais


def login(api, senha=ANTIGA):
    return chamar(api, '/auth/login', method='POST', form=True, dados={'username': EMAIL, 'password': senha})


def post(api, path, dados=None, token=None):
    return chamar(api, '/auth/' + path, method='POST', dados=dados, token=token)


def test_login_logout_tokens_sem_sessao_e_expirados(api, pg, equipe):
    from app.core.security import SECRET_KEY, ALGORITHM, criar_token, expira_token

    primeiro = login(api)
    assert primeiro[0] == 200, primeiro
    a, b = primeiro[1]['access_token'], login(api)[1]['access_token']
    assert a != b
    assert chamar(api, '/auth/me', token=a)[1]['perfil'] == 'admin'
    assert chamar(api, '/filiais', token=a)[0] == 200
    assert post(api, 'logout', token=a)[0] == 204
    assert chamar(api, '/auth/me', token=a)[0] == 401
    assert chamar(api, '/auth/me', token=b)[0] == 200
    antigo = jwt.encode({'sub': str(equipe['admin']), 'exp': expira_token()}, SECRET_KEY, algorithm=ALGORITHM)
    expirado = criar_token(equipe['admin'], uuid4(), datetime.now(timezone.utc) - timedelta(seconds=1))
    sem_sessao = criar_token(equipe['admin'], uuid4(), expira_token())
    for token in (antigo, expirado, sem_sessao):
        assert chamar(api, '/auth/me', token=token)[0] == 401
    with pg.begin() as conn:
        conn.execute(text("UPDATE equipe_sessoes SET expira_em=now()-interval '1 second'"))
    assert chamar(api, '/auth/me', token=b)[0] == 401
    assert login(api)[0] == 200
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM equipe_sessoes')) == 1


def test_troca_revoga_todas_as_sessoes(api, equipe):
    a, b = (login(api)[1]['access_token'] for _ in range(2))
    assert post(api, 'trocar-senha', {'senha_atual': NOVA, 'senha': NOVA}, a)[0] == 400
    assert post(api, 'trocar-senha', {'senha_atual': ANTIGA, 'senha': NOVA}, a)[0] == 204
    assert all(chamar(api, '/auth/me', token=t)[0] == 401 for t in (a,b))
    assert login(api)[0] == 401 and login(api, NOVA)[0] == 200


def test_recuperacao_neutra_pos_resposta_e_uso_unico(api, pg, equipe, monkeypatch):
    from app.services import entrega_codigo_cliente as entrega

    terminou = []
    entregues = []
    async def observar(scope, receive, send):
        async def observado(message):
            await send(message)
            if message['type'] == 'http.response.body':
                terminou.append(True)
        await api(scope, receive, observado)

    def enviar(email, codigo):
        assert terminou
        entregues.append((email, codigo))
    monkeypatch.setattr(entrega, 'enviar', enviar)

    def pedir(email):
        terminou.clear()
        status, resposta = post(observar, 'recuperar', {'email': email})
        assert status == 202
        return resposta

    a, b = (login(api)[1]['access_token'] for _ in range(2))
    encontrado = pedir(EMAIL)
    ausente = pedir('ausente@example.com')
    assert encontrado['mensagem'] == ausente['mensagem']
    assert encontrado.keys() == ausente.keys()
    (destinatario, codigo), = entregues
    assert destinatario == EMAIL
    payload = {'solicitacao_id': encontrado['solicitacao_id'], 'codigo': codigo, 'senha': NOVA}
    assert post(api, 'redefinir', payload)[0] == 204
    assert post(api, 'redefinir', payload)[0] == 400
    assert all(chamar(api, '/auth/me', token=t)[0] == 401 for t in (a,b))
    assert login(api)[0] == 401 and login(api, NOVA)[0] == 200
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT senha_hash FROM usuarios WHERE id=:id'), {'id': equipe['admin']}).startswith('$argon2')


def test_limites_inativo_expirado_e_falha_smtp(api, pg, equipe, monkeypatch):
    from app.services import entrega_codigo_cliente as entrega, portal_cliente, recuperacao_equipe as recuperacao

    instante = datetime.now(timezone.utc)
    monkeypatch.setattr(portal_cliente, 'agora', lambda: instante)
    monkeypatch.setattr(recuperacao, 'agora', lambda: instante)
    codigos = []
    monkeypatch.setattr(entrega, 'enviar', lambda _, codigo: codigos.append(codigo))

    def pedir(email=EMAIL):
        status, dados = post(api, 'recuperar', {'email': email})
        assert status == 202 and dados['mensagem'] == recuperacao.MENSAGEM
        return dados['solicitacao_id']

    def redefinir(id_, codigo):
        return post(api, 'redefinir', {'solicitacao_id':id_, 'codigo':codigo, 'senha':NOVA})[0]

    primeiro = pedir()
    pedir()
    assert len(codigos) == 1
    errado = '000000' if codigos[0] != '000000' else '000001'
    for _ in range(5):
        assert redefinir(primeiro, errado) == 400
    assert redefinir(primeiro, codigos[0]) == 400

    instante += timedelta(seconds=61)
    segundo = pedir()
    assert len(codigos) == 2
    instante += timedelta(minutes=10)
    assert redefinir(segundo, codigos[-1]) == 400
    terceiro = pedir()
    with pg.begin() as conn:
        conn.execute(text('UPDATE usuarios SET ativo=false WHERE id=:id'), {'id':equipe['admin']})
    assert redefinir(terceiro, codigos[-1]) == 400
    instante += timedelta(seconds=61)
    pedir()
    assert len(codigos) == 3
    with pg.begin() as conn:
        conn.execute(text('UPDATE usuarios SET ativo=true WHERE id=:id'), {'id':equipe['admin']})
    instante += timedelta(seconds=61)
    def falhar(_, codigo):
        codigos.append(codigo)
        raise entrega.EntregaIndisponivel()
    monkeypatch.setattr(entrega, 'enviar', falhar)
    falhou = pedir()
    assert redefinir(falhou, codigos[-1]) == 400
    instante += timedelta(seconds=61)
    pedir()
    assert len(codigos) == 4
    for n in range(12):
        pedir(f'ausente{n}@example.com')
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT max(quantidade) FROM portal_clientes_limites')) == 10
        for tabela in ('equipe_sessoes', 'equipe_recuperacoes'):
            for papel in ('anon','authenticated','service_role'):
                assert not conn.scalar(text("SELECT has_table_privilege(:p,:t,'SELECT,INSERT,UPDATE,DELETE')"),
                                       {'p':papel,'t':'public.' + tabela})
