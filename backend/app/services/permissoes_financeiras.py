"""Preparação para recebimento e fechamento; não concede acesso a relatórios.

O chamador deve reler o usuário ativo, autorizar e bloquear a filial e
reler a comanda bloqueada antes de aplicar esta política ao seu barbeiro_id.
Esta política não substitui isolamento por filial nem valida saldo ou estados.
Usada pelos serviços financeiros; não concede acesso a relatórios ou rotas.
"""
from uuid import UUID

from app.models.usuario import PerfilEnum, Usuario
from app.services.errors import SemPermissao


def autorizar_recebimento_ou_fechamento(usuario: Usuario, barbeiro_id: UUID) -> None:
    """Gestores operam na filial autorizada; ambos os barbeiros, somente próprias."""
    if not usuario.ativo or usuario.perfil not in tuple(PerfilEnum):
        raise SemPermissao("Sem permissão para operar financeiramente a comanda")
    if usuario.perfil in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
        return
    if usuario.id != barbeiro_id:
        raise SemPermissao("Sem permissão para operar financeiramente a comanda")
