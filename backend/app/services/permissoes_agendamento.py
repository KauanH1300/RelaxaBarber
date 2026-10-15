"""Políticas de agenda; chefe amplia somente o escopo de leitura."""
from uuid import UUID

from app.models.usuario import PerfilEnum, Usuario
from app.services.errors import SemPermissao

PERFIS_GESTAO_AGENDA = (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO)
PERFIS_LEITURA_GLOBAL = (*PERFIS_GESTAO_AGENDA, PerfilEnum.BARBEIRO_CHEFE)


def validar_perfil(usuario: Usuario) -> None:
    if usuario.perfil not in tuple(PerfilEnum):
        raise SemPermissao("Sem permissão")


def pode_operar_profissional(usuario: Usuario, barbeiro_id: UUID) -> bool:
    validar_perfil(usuario)
    return usuario.perfil in PERFIS_GESTAO_AGENDA or usuario.id == barbeiro_id


def escopo_consulta(usuario: Usuario, barbeiro_id: UUID | None) -> UUID | None:
    validar_perfil(usuario)
    if usuario.perfil in PERFIS_LEITURA_GLOBAL:
        return barbeiro_id
    if barbeiro_id is not None and barbeiro_id != usuario.id:
        raise SemPermissao("Sem permissão para consultar a agenda de outro profissional")
    return usuario.id
