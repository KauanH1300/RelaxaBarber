from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from fastapi import HTTPException
from sqlalchemy.orm import Session

from test_sessoes_equipe import equipe, login, post, EMAIL, ANTIGA, NOVA
from test_financeiro_http import api
from test_contexto_filiais import duas_filiais
from test_concorrencia import data


def test_login_e_troca_senha_limitados_sem_bloqueio_permanente(api, equipe, monkeypatch):
    from app.services import portal_cliente
    for _ in range(5):
        assert login(api, "errada")[0] == 401
    assert login(api)[0] == 429
    instante = portal_cliente.agora()
    monkeypatch.setattr(portal_cliente, "agora", lambda: instante + timedelta(minutes=16))
    token = login(api)[1]["access_token"]
    for _ in range(5):
        assert post(api, "trocar-senha", {"senha_atual": "errada", "senha": NOVA}, token)[0] == 400
    assert post(api, "trocar-senha", {"senha_atual": ANTIGA, "senha": NOVA}, token)[0] == 429
    # Limite de troca é independente do login.
    assert login(api)[0] == 200


def test_contadores_concorrentes_por_conta_e_por_ip(runtime_pg):
    from app.services.limites_senha import admitir

    def lote(finalidade, quantidade, conta_fixa):
        barreira = Barrier(quantidade)
        def tentar(indice):
            with Session(runtime_pg) as db:
                barreira.wait(timeout=15)
                try:
                    admitir(db, finalidade, f"ip-{indice}" if conta_fixa else "mesmo-ip",
                            "mesma-conta" if conta_fixa else f"conta-{indice}")
                    return True
                except HTTPException as erro:
                    assert erro.status_code == 429
                    return False
        with ThreadPoolExecutor(max_workers=quantidade) as pool:
            return sum(pool.map(tentar, range(quantidade)))
    assert lote("login", 8, True) == 5
    # Sem estourar o pool de quatro conexões da fixture.
    with Session(runtime_pg) as db:
        for indice in range(30):
            admitir(db, "login-ip", "ip-unico", f"conta-{indice}")
        try:
            admitir(db, "login-ip", "ip-unico", "outra-conta")
            assert False
        except HTTPException as erro:
            assert erro.status_code == 429


def test_senha_antiga_curta_e_rehash_transacional(api, pg, equipe):
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from app.models import Usuario
    from argon2 import extract_parameters
    with Session(pg) as db, db.begin():
        db.get(Usuario, equipe["admin"]).senha_hash = PasswordHash((
            Argon2Hasher(time_cost=1, memory_cost=8192),)).hash("curta")
    assert login(api, "curta")[0] == 200
    with Session(pg) as db:
        assert extract_parameters(db.get(Usuario, equipe["admin"]).senha_hash).memory_cost == 65536



def test_cliente_senha_curta_antiga_rehash_preserva_sessao(runtime_pg):
    from app.models import Cliente, ContaPortalCliente
    from app.schemas.portal_cliente import LoginPortal
    from app.services import portal_cliente
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from argon2 import extract_parameters
    with Session(runtime_pg) as db:
        cliente = Cliente(nome="Cliente legado", telefone="81999991234", email="legado@example.com",
                          conta_ativada=True, senha_hash=PasswordHash((
                              Argon2Hasher(time_cost=1, memory_cost=8192),)).hash("curta"))
        db.add(cliente)
        db.flush()
        ident = cliente.id
        db.add(ContaPortalCliente(cliente_id=ident, email_confirmado=cliente.email))
        db.commit()
        token = portal_cliente.login(db, LoginPortal(email=cliente.email, senha="curta"), "ip-legado")
        assert portal_cliente.autenticar(db, token).id == ident
        assert extract_parameters(db.get(Cliente, ident).senha_hash).memory_cost == 65536


def test_todos_perfis_login_e_respostas_genericas(api, pg, equipe):
    from app.models import Usuario, PerfilEnum
    from test_seguranca_horarios import chamar
    for perfil in PerfilEnum:
        with Session(pg) as db, db.begin():
            db.get(Usuario, equipe["admin"]).perfil = perfil
        assert login(api)[0] == 200
    ausente = chamar(api, "/auth/login", method="POST", form=True,
                     dados={"username": "ausente@example.com", "password": ANTIGA})
    assert ausente[0] == 401
    with Session(pg) as db, db.begin():
        db.get(Usuario, equipe["admin"]).ativo = False
    inativo = login(api)
    assert inativo[0:2] == ausente[0:2]
