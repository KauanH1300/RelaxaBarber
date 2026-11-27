from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import exigir_perfil, get_current_user, oauth2
from app.core.security import hash_senha, verificar_senha
from app.db.database import get_db
from app.models.usuario import PERFIS_PROFISSIONAIS, PerfilEnum, Usuario
from app.services.errors import SemPermissao, FilialObrigatoria
from app.services import filiais
from app.models.usuario_filial import UsuarioFilial
from app.services.permissoes_agendamento import escopo_consulta
from app.schemas.usuario import UsuarioCreate, UsuarioOut, ProfissionalOut, UsuarioUpdate
from app.services import gestao_usuarios, recuperacao_equipe, sessoes_equipe
from app.schemas.equipe_auth import RecuperacaoAdministrativa
from app.services.limites_senha import admitir
from app.services.errors import RecursoNaoEncontrado, ConflitoGestaoFilial

from app.services.persistencia import transacao_escrita, recarregar_confirmado
from app.services.cadastro_idempotente import id_cadastro, travar_cadastro

router = APIRouter(prefix="/usuarios", tags=["usuarios"])


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    dados: UsuarioCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
    chave: Annotated[UUID | None, Header(alias='Idempotency-Key')] = None,
):
    with transacao_escrita(db):
        try:
            atual = filiais.usuario_atual(db, _, bloquear=True)
            if atual.perfil != PerfilEnum.ADMIN:
                raise SemPermissao("Sem permissão")
            ids = dados.filial_ids
            if ids:
                unidades = [
                    filiais.resolver_filial(db, atual, filial_id, bloquear=True)
                    for filial_id in sorted(set(ids), key=str)
                ]
            else:
                unidades = [filiais.resolver_filial(db, atual, bloquear=True)]
        except SemPermissao as exc:
            raise HTTPException(403, str(exc)) from exc
        except FilialObrigatoria as exc:
            raise HTTPException(422, str(exc)) from exc
        ident = id_cadastro('usuario', atual.id, chave) if chave else None
        if ident:
            travar_cadastro(db, ident)
            anterior = db.get(Usuario, ident)
            if anterior is not None:
                return anterior
        email = dados.email.lower()
        if db.scalar(select(Usuario).where(Usuario.email == email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado")

        usuario = Usuario(
            id=ident,
            nome=dados.nome,
            email=email,
            telefone=dados.telefone,
            senha_hash=hash_senha(dados.senha),
            perfil=dados.perfil,
        )
        db.add(usuario)
        db.flush()
        db.add_all([UsuarioFilial(usuario_id=usuario.id, filial_id=unidade.id) for unidade in unidades])
    recarregar_confirmado(db, usuario)
    return usuario


@router.get('/cadastros/{chave}', response_model=UsuarioOut)
def conferir_cadastro(chave: UUID, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN))):
    anterior = db.get(Usuario, id_cadastro('usuario', usuario.id, chave))
    if anterior is None:
        raise HTTPException(404, 'Cadastro ainda não localizado')
    return anterior


@router.get("", response_model=list[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    return db.scalars(select(Usuario).order_by(Usuario.nome)).all()


@router.patch('/{usuario_id}', response_model=UsuarioOut)
def atualizar_usuario(
    usuario_id: UUID, dados: UsuarioUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    try:
        return gestao_usuarios.atualizar(db, usuario, usuario_id, dados)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except ConflitoGestaoFilial as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get("/barbeiros", response_model=list[ProfissionalOut])
def listar_barbeiros(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    filial_id: UUID | None = None,
):
    try:
        usuario = filiais.usuario_atual(db, usuario)
        filial = filiais.resolver_filial(db, usuario, filial_id)
        profissional_id = escopo_consulta(usuario, None)
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    query = select(Usuario).join(UsuarioFilial, UsuarioFilial.usuario_id == Usuario.id).where(
        UsuarioFilial.filial_id == filial.id, UsuarioFilial.ativo.is_(True),
        Usuario.ativo.is_(True), Usuario.perfil.in_(PERFIS_PROFISSIONAIS),
    )
    if profissional_id is not None:
        query = query.where(Usuario.id == profissional_id)
    return db.scalars(query.order_by(Usuario.nome)).all()


@router.post('/{usuario_id}/recuperacao-administrativa', status_code=204)
def recuperar_funcionario(usuario_id: UUID, dados: RecuperacaoAdministrativa, request: Request, token: str = Depends(oauth2),
                           db: Session = Depends(get_db),
                           usuario: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN))):
    admitir(db, 'recuperacao-administrativa', request.client.host if request.client else 'desconhecido',
            str(usuario.id))
    with transacao_escrita(db):
        ids = (usuario.id, usuario_id)
        usuarios = {u.id: u for u in db.scalars(select(Usuario).where(Usuario.id.in_(ids))
                    .order_by(Usuario.id).with_for_update().execution_options(populate_existing=True))}
        ator = usuarios.get(usuario.id)
        if (not ator or not ator.ativo or ator.perfil != PerfilEnum.ADMIN or not ator.email_confirmado_em
                or not sessoes_equipe.validar(db, token)
                or not verificar_senha(dados.senha_atual_admin, ator.senha_hash)):
            raise HTTPException(403, 'Confirme sua senha de administrador.')
        alvo = usuarios.get(usuario_id)
        if not alvo or not alvo.ativo or alvo.perfil == PerfilEnum.ADMIN or alvo.email_confirmado_em:
            raise HTTPException(409, 'Funcionário indisponível para recuperação administrativa.')
        recuperacao_equipe.alterar_senha(db, alvo, dados.senha)
        db.execute(text("""
            INSERT INTO public.equipe_recuperacoes_auditoria (id, ator_id, usuario_id, motivo)
            VALUES (:id, :ator_id, :usuario_id, :motivo)
        """), dict(id=uuid4(), ator_id=ator.id, usuario_id=alvo.id, motivo=dados.motivo))
