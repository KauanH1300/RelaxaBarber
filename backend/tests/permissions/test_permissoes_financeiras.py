"""Política preparatória pura: sem banco, autenticação real ou operações financeiras."""
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.parametrize("perfil", ["admin", "recepcao", "barbeiro", "barbeiro_chefe"])
@pytest.mark.parametrize("propria", [True, False])
def test_escopo_por_profissional(isolated_runtime, perfil, propria):
    from app.services.errors import SemPermissao
    from app.services.permissoes_financeiras import autorizar_recebimento_ou_fechamento

    usuario = SimpleNamespace(id=uuid4(), perfil=perfil, ativo=True)
    profissional = usuario.id if propria else uuid4()
    if propria or perfil in ("admin", "recepcao"):
        assert autorizar_recebimento_ou_fechamento(usuario, profissional) is None
    else:
        with pytest.raises(SemPermissao):
            autorizar_recebimento_ou_fechamento(usuario, profissional)


@pytest.mark.parametrize("perfil", ["admin", "recepcao", "barbeiro", "barbeiro_chefe"])
def test_inativo_nao_pode_operar_nem_propria(isolated_runtime, perfil):
    from app.services.errors import SemPermissao
    from app.services.permissoes_financeiras import autorizar_recebimento_ou_fechamento

    usuario = SimpleNamespace(id=uuid4(), perfil=perfil, ativo=False)
    with pytest.raises(SemPermissao):
        autorizar_recebimento_ou_fechamento(usuario, usuario.id)


@pytest.mark.parametrize("perfil", [None, "desconhecido"])
def test_perfil_desconhecido_nao_pode_operar_propria(isolated_runtime, perfil):
    from app.services.errors import SemPermissao
    from app.services.permissoes_financeiras import autorizar_recebimento_ou_fechamento

    usuario = SimpleNamespace(id=uuid4(), perfil=perfil, ativo=True)
    with pytest.raises(SemPermissao):
        autorizar_recebimento_ou_fechamento(usuario, usuario.id)
