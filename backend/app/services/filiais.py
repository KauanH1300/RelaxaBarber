"""Contexto autorizado, sempre relido do banco; JWT não transporta privilégios.

Escritas mantêm locks compartilhados em usuário, empresa, filial e vínculos
até o commit. Reservas concorrentes continuam arbitradas pela EXCLUDE global.
Não há gestão de atividade nesta etapa; futuras escritas de gestão devem seguir
esta ordem antes de bloquear agendamento e comanda.
"""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Empresa, Filial, Usuario, UsuarioFilial, PerfilEnum
from app.models.usuario import PERFIS_PROFISSIONAIS
from app.services.errors import SemPermissao, RecursoNaoEncontrado, FilialObrigatoria
from app.services.permissoes_agendamento import escopo_consulta


def usuario_atual(db: Session, usuario: Usuario, bloquear=False) -> Usuario:
    query = select(Usuario).where(Usuario.id == usuario.id, Usuario.ativo.is_(True)).execution_options(populate_existing=True)
    if bloquear:
        query = query.with_for_update(read=True)
    atual = db.scalar(query)
    if atual is None:
        raise SemPermissao("Usuário sem acesso ativo")
    return atual


def consulta_autorizadas(usuario: Usuario):
    query = select(Filial).join(Empresa).where(Filial.ativa.is_(True), Empresa.ativa.is_(True))
    if usuario.perfil != PerfilEnum.ADMIN:
        query = query.where(select(UsuarioFilial.id).where(
            UsuarioFilial.usuario_id == usuario.id,
            UsuarioFilial.filial_id == Filial.id,
            UsuarioFilial.ativo.is_(True),
        ).exists())
    return query.order_by(Filial.nome, Filial.id)


def listar_filiais(db, usuario):
    usuario = usuario_atual(db, usuario)
    escopo_consulta(usuario, None)  # nega perfis desconhecidos
    return db.scalars(consulta_autorizadas(usuario)).all()


def validar_vinculo(db, usuario_id, filial_id, bloquear=False):
    query = select(UsuarioFilial).where(
        UsuarioFilial.usuario_id == usuario_id, UsuarioFilial.filial_id == filial_id,
        UsuarioFilial.ativo.is_(True),
    ).execution_options(populate_existing=True)
    if bloquear:
        query = query.with_for_update(read=True)
    if db.scalar(query) is None:
        raise SemPermissao("Sem vínculo ativo com a filial")


def resolver_filial(db, usuario, filial_id: UUID | None = None, bloquear=False):
    usuario = usuario_atual(db, usuario, bloquear)
    escopo_consulta(usuario, None)
    if bloquear:
        # Empresa única é linha estável; SHARE permite reservas simultâneas.
        db.scalars(select(Empresa).order_by(Empresa.id).with_for_update(read=True)).all()
    query = consulta_autorizadas(usuario)
    if filial_id is not None:
        query = query.where(Filial.id == filial_id)
    if bloquear:
        query = query.with_for_update(read=True, of=Filial)
    unidades = db.scalars(query.execution_options(populate_existing=True)).all()
    if not unidades:
        raise SemPermissao("Sem acesso à filial")
    if len(unidades) != 1:
        raise FilialObrigatoria("Informe filial_id para selecionar uma das filiais autorizadas")
    filial = unidades[0]
    if usuario.perfil != PerfilEnum.ADMIN:
        validar_vinculo(db, usuario.id, filial.id, bloquear)
    return filial


def validar_profissional(db, profissional_id, filial_id):
    query = select(Usuario).where(
        Usuario.id == profissional_id, Usuario.ativo.is_(True),
        Usuario.perfil.in_(PERFIS_PROFISSIONAIS),
    ).with_for_update(read=True).execution_options(populate_existing=True)
    if db.scalar(query) is None:
        raise RecursoNaoEncontrado("Profissional ativo não encontrado")
    validar_vinculo(db, profissional_id, filial_id, bloquear=True)


def filtro_acesso(usuario, model, escrita=False):
    profissional_id = escopo_consulta(usuario, None)
    if escrita and usuario.perfil in (PerfilEnum.BARBEIRO, PerfilEnum.BARBEIRO_CHEFE):
        profissional_id = usuario.id
    unidades = consulta_autorizadas(usuario).with_only_columns(Filial.id).order_by(None)
    filtros = [model.filial_id.in_(unidades)]
    if profissional_id is not None:
        filtros.append(model.barbeiro_id == profissional_id)
    return filtros


def filial_do_registro(db, usuario, model, registro_id, escrita=False):
    usuario = usuario_atual(db, usuario)
    filial_id = db.scalar(select(model.filial_id).where(
        model.id == registro_id, *filtro_acesso(usuario, model, escrita),
    ))
    if filial_id is None:
        raise RecursoNaoEncontrado("Recurso não encontrado")
    return filial_id
