from concurrent.futures import ThreadPoolExecutor
from threading import Event
import importlib
import pytest


def test_politica_comprimentos_blocklist_e_frases(isolated_runtime):
    from pydantic import TypeAdapter, ValidationError
    from app.core.senhas import SenhaCliente, SenhaEquipe
    cliente, equipe = TypeAdapter(SenhaCliente), TypeAdapter(SenhaEquipe)
    for adaptador, minimo in ((cliente, 8), (equipe, 15)):
        assert adaptador.validate_python("á" * minimo) == "á" * minimo
        assert adaptador.validate_python("á" * 128) == "á" * 128
        assert adaptador.validate_python("uma frase com password e espaços") == "uma frase com password e espaços"
        for senha in ("x" * (minimo - 1), "á" * 129, "passwordpassword", "123456789012345"):
            with pytest.raises(ValidationError):
                adaptador.validate_python(senha)
    assert cliente.validate_python(" espaço ") == " espaço "


def test_argon_parametros_legado_rehash_e_salt(isolated_runtime):
    from argon2 import extract_parameters, Type
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    security = importlib.import_module("app.core.security")
    hash_ = security.hash_senha("curta")
    params = extract_parameters(hash_)
    assert (params.type, params.version, params.memory_cost, params.time_cost,
            params.parallelism, params.salt_len, params.hash_len) == (Type.ID, 19, 65536, 3, 4, 16, 32)
    assert security.hash_senha("curta") != hash_
    assert security.autenticar_senha("curta", hash_) == (True, None)
    antigo = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192),)).hash("curta")
    valido, novo = security.autenticar_senha("curta", antigo)
    assert valido and novo and extract_parameters(novo).memory_cost == 65536
    assert security.autenticar_senha("errada", antigo) == (False, None)


def test_argon_recusa_excesso_simultaneo_e_libera_slot(isolated_runtime, monkeypatch):
    from fastapi import HTTPException
    security = importlib.import_module("app.core.security")
    entrou, liberar = Event(), Event()

    def lento(*args):
        entrou.set()
        assert liberar.wait(5)
        return True, None

    monkeypatch.setattr(security._hasher, "verify_and_update", lento)
    with ThreadPoolExecutor(max_workers=2) as pool:
        primeira = pool.submit(security.autenticar_senha, "senha", "hash")
        assert entrou.wait(5)
        try:
            with pytest.raises(HTTPException) as erro:
                security.autenticar_senha("outra", "hash")
            assert erro.value.status_code == 503
        finally:
            liberar.set()
        assert primeira.result() == (True, None)
    assert security.autenticar_senha("senha", "hash") == (True, None)
