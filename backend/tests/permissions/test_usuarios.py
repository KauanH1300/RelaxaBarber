import asyncio
import importlib
import inspect
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException

PROFILES = ["admin", "recepcao", "barbeiro_chefe", "barbeiro"]


@pytest.fixture(autouse=True)
def synchronous_test_dispatch(monkeypatch):
    # O sandbox não despacha o threadpool AnyIO de forma confiável. Executar
    # funções síncronas no loop mantém DI/serialização/HTTP reais nestes testes
    # sem threads, rede ou banco. Não é teste de concorrência.
    import fastapi.dependencies.utils
    import fastapi.routing

    async def inline_call(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(fastapi.dependencies.utils, "run_in_threadpool", inline_call)
    monkeypatch.setattr(fastapi.routing, "run_in_threadpool", inline_call)


@pytest.fixture
def usuarios_routes(isolated_runtime):
    return importlib.import_module("app.api.routes.usuarios")


async def asgi_get(app, path):
    """Cliente ASGI mínimo sem httpx ou servidor/conexões de rede."""
    messages = []
    sent = False
    async def receive():
        nonlocal sent
        if sent:
            await asyncio.Event().wait()
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        messages.append(message)
    await asyncio.wait_for(app({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
        "query_string": b"", "root_path": "", "headers": [],
        "server": ("test", 80), "client": ("test", 1),
    }, receive, send), timeout=5)
    status = next(m["status"] for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return status, json.loads(body)


@pytest.mark.parametrize("profile", PROFILES)
def test_endpoint_barbeiros_escopo_e_resposta(usuarios_routes, isolated_runtime, profile):
    from app.api.deps import get_current_user
    from app.db.database import get_db

    user = SimpleNamespace(id=uuid4(), perfil=profile)
    records = [SimpleNamespace(id=user.id, nome="Ana", email="nao-expor@example.test", perfil="barbeiro")]
    if profile != "barbeiro":
        records.append(SimpleNamespace(id=uuid4(), nome="Beto", perfil="barbeiro_chefe"))
    db = MagicMock()
    db.scalars.return_value.all.return_value = records
    app = FastAPI()
    app.include_router(usuarios_routes.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    status, body = asyncio.run(asgi_get(app, "/usuarios/barbeiros"))
    assert status == 200
    assert [r["nome"] for r in body] == [r.nome for r in records]
    assert all(set(row) == {"id", "nome"} for row in body)
    query = db.scalars.call_args.args[0]
    sql = str(query)
    assert "usuarios.ativo IS true" in sql
    assert "ORDER BY usuarios.nome" in sql
    values = list(query.compile().params.values())
    assert any(set(v) == {"barbeiro", "barbeiro_chefe"} for v in values if isinstance(v, (list, tuple)))
    if profile == "barbeiro":
        assert user.id in values
        assert "usuarios.id =" in sql
    else:
        assert "usuarios.id =" not in sql


@pytest.mark.parametrize("profile", PROFILES)
def test_gestao_usuarios_permanece_admin(usuarios_routes, isolated_runtime, profile):
    from app.api.deps import get_current_user
    from app.db.database import get_db

    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    app = FastAPI()
    app.include_router(usuarios_routes.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), perfil=profile)
    app.dependency_overrides[get_db] = lambda: db
    status, _ = asyncio.run(asgi_get(app, "/usuarios"))
    assert status == (200 if profile == "admin" else 403)
    if profile != "admin":
        db.scalars.assert_not_called()
    # A dependência de criação também continua limitada ao administrador.
    dependency = inspect.signature(usuarios_routes.criar_usuario).parameters["_"].default.dependency
    user = SimpleNamespace(id=uuid4(), perfil=profile)
    if profile == "admin":
        assert dependency(usuario=user) is user
    else:
        with pytest.raises(HTTPException) as exc:
            dependency(usuario=user)
        assert exc.value.status_code == 403


def test_barbeiros_exige_autenticacao(usuarios_routes, isolated_runtime):
    from app.api.deps import get_current_user
    app = FastAPI()
    app.include_router(usuarios_routes.router)
    def anonymous():
        raise HTTPException(401, "Não autenticado")
    app.dependency_overrides[get_current_user] = anonymous
    status, _ = asyncio.run(asgi_get(app, "/usuarios/barbeiros"))
    assert status == 401


def test_enum_e_cliente_independente(models, isolated_runtime):
    from app.schemas.usuario import UsuarioCreate
    from app.schemas.cliente import ClienteCreate
    from app.db.database import Base

    assert "BARBEIRO_CHEFE" in models.Usuario.__table__.c.perfil.type.enums
    assert models.PerfilEnum.BARBEIRO_CHEFE.value == "barbeiro_chefe"
    assert len(models.PerfilEnum) == 4
    assert UsuarioCreate(nome="Chefe", email="chefe@example.com", senha="senha-ficticia", perfil="barbeiro_chefe").perfil == models.PerfilEnum.BARBEIRO_CHEFE
    assert models.Cliente.__table__.name == "clientes"
    assert models.Usuario.__table__.name == "usuarios"
    assert "usuario_id" not in models.Cliente.__table__.c
    assert models.Cliente.__table__.c.senha_hash.nullable
    assert ClienteCreate(nome="Sem senha", telefone="81999999999").nome == "Sem senha"
    assert set(Base.metadata.tables) == {
        "usuarios", "clientes", "servicos", "agendamentos", "agendamento_servicos", "comandas", "itens_comanda",
    }
