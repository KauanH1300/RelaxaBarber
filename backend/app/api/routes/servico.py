import uuid
from typing import Annotated
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Response, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.models.usuario import Usuario
from app.api.deps import get_db, exigir_perfil, get_current_user
from app.models.usuario import PerfilEnum
from app.models.servico import CategoriaServico, Servico
from app.schemas.servico import (
    CategoriaServicoCreate, CategoriaServicoOut, ServicoCreate, ServicoUpdate, ServicoOut, ServicoCatalogoOut,
)

from app.services.persistencia import transacao_escrita, recarregar_confirmado
from app.services.cadastro_idempotente import id_cadastro, travar_cadastro

from app.schemas.insumo import InsumoPadrao
from app.services import filiais, insumos_servico
from app.services.errors import FilialObrigatoria, HorarioAgendamentoInvalido, RecursoNaoEncontrado, SemPermissao

router = APIRouter(prefix="/servicos", tags=["Serviços"])


oauth2_opcional = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def usuario_catalogo(
    token: str | None = Depends(oauth2_opcional),
    db: Session = Depends(get_db),
) -> Usuario | None:
    # Credenciais fornecidas devem ser validadas; ausência mantém catálogo público.
    return get_current_user(token, db) if token is not None else None


def resposta_servico(servico: Servico, usuario: Usuario | None):
    schema = ServicoOut if usuario and usuario.perfil == PerfilEnum.ADMIN else ServicoCatalogoOut
    return schema.model_validate(servico)


@router.get("/", response_model=list[ServicoOut | ServicoCatalogoOut])
def listar_servicos(
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_catalogo),
):
    """Catálogo ativo público; apenas administrador recebe comissão e datas."""
    return [resposta_servico(servico, usuario)
            for servico in db.query(Servico).options(selectinload(Servico.categorias)).filter(Servico.ativo == True).all()]


@router.get("/categorias", response_model=list[CategoriaServicoOut])
def listar_categorias(
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    return db.scalars(select(CategoriaServico).order_by(CategoriaServico.nome)).all()


@router.post("/categorias", response_model=CategoriaServicoOut)
def cadastrar_categoria(
    dados: CategoriaServicoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    nome_normalizado = dados.nome.casefold()
    with transacao_escrita(db):
        db.execute(insert(CategoriaServico).values(nome=dados.nome, nome_normalizado=nome_normalizado)
                   .on_conflict_do_nothing(index_elements=[CategoriaServico.nome_normalizado]))
        categoria = db.scalars(select(CategoriaServico).where(
            CategoriaServico.nome_normalizado == nome_normalizado)).one()
        return CategoriaServicoOut.model_validate(categoria)


def selecionar_categorias(db: Session, ids: list[uuid.UUID]) -> list[CategoriaServico]:
    if not ids:
        return []
    categorias = list(db.scalars(select(CategoriaServico).where(CategoriaServico.id.in_(ids))))
    if len(categorias) != len(set(ids)):
        raise HTTPException(status_code=422, detail="Uma ou mais categorias de serviço não existem.")
    return categorias


@router.get("/{servico_id}", response_model=ServicoOut | ServicoCatalogoOut)
def consultar_servico(
    servico_id: uuid.UUID,
    db: Session = Depends(get_db),
    usuario: Usuario | None = Depends(usuario_catalogo),
):
    """Inativos são consultáveis apenas por administrador; demais recebem 404."""
    consulta = db.query(Servico).filter(Servico.id == servico_id)
    if not usuario or usuario.perfil != PerfilEnum.ADMIN:
        consulta = consulta.filter(Servico.ativo == True)
    servico = consulta.first()
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return resposta_servico(servico, usuario)


@router.get('/{servico_id}/insumos', response_model=list[InsumoPadrao])
def consultar_insumos(servico_id: uuid.UUID, filial_id: uuid.UUID, db: Session = Depends(get_db),
                      usuario=Depends(exigir_perfil(PerfilEnum.ADMIN)), response: Response = None):
    try:
        filial = filiais.resolver_filial(db, usuario, filial_id)
        itens = insumos_servico.listar(db, servico_id, filial.id)
        if response is not None:
            response.headers.update({'ETag': insumos_servico.versao_insumos(itens), 'Cache-Control': 'no-store'})
        return itens
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put('/{servico_id}/insumos', response_model=list[InsumoPadrao])
def salvar_insumos(servico_id: uuid.UUID, filial_id: uuid.UUID,
                   itens: Annotated[list[InsumoPadrao], Body(max_length=100)], db: Session = Depends(get_db),
                   usuario=Depends(exigir_perfil(PerfilEnum.ADMIN)), response: Response = None,
                   versao: Annotated[str | None, Header(alias='If-Match')] = None):
    try:
        with transacao_escrita(db):
            atual = filiais.usuario_atual(db, usuario, bloquear=True)
            if atual.perfil != PerfilEnum.ADMIN:
                raise SemPermissao('Somente ADMIN pode configurar insumos')
            filial = filiais.resolver_filial(db, atual, filial_id, bloquear=True)
            insumos_servico.configurar(db, servico_id, filial.id, itens, versao)
        if response is not None:
            response.headers['ETag'] = insumos_servico.versao_insumos(itens)
        return itens
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except (FilialObrigatoria, HorarioAgendamentoInvalido) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/", response_model=ServicoOut, status_code=status.HTTP_201_CREATED)
def criar_servico(
    servico: ServicoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
    chave: Annotated[uuid.UUID | None, Header(alias='Idempotency-Key')] = None,
):
    with transacao_escrita(db):
        ident = id_cadastro('servico', _.id, chave) if chave else None
        if ident:
            travar_cadastro(db, ident)
            anterior = db.get(Servico, ident)
            if anterior is not None:
                return anterior
        novo = Servico(id=ident, **servico.model_dump(exclude={"categorias_ids"}))
        novo.categorias = selecionar_categorias(db, servico.categorias_ids)
        db.add(novo)
    recarregar_confirmado(db, novo)
    return novo


@router.get('/cadastros/{chave}', response_model=ServicoOut)
def conferir_cadastro(chave: uuid.UUID, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN))):
    anterior = db.get(Servico, id_cadastro('servico', usuario.id, chave))
    if anterior is None:
        raise HTTPException(404, 'Cadastro ainda não localizado')
    return anterior


@router.put("/{servico_id}", response_model=ServicoOut)
def atualizar_servico(
    servico_id: uuid.UUID,
    dados: ServicoUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    with transacao_escrita(db):
        servico = db.query(Servico).filter(Servico.id == servico_id).with_for_update().first()
        if not servico:
            raise HTTPException(status_code=404, detail="Serviço não encontrado")

        if dados.categorias_ids is not None:
            servico.categorias = selecionar_categorias(db, dados.categorias_ids)

        for campo, valor in dados.model_dump(exclude_unset=True, exclude={"categorias_ids"}).items():
            setattr(servico, campo, valor)

    recarregar_confirmado(db, servico)
    return servico


@router.delete("/{servico_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_servico(
    servico_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    with transacao_escrita(db):
        servico = db.query(Servico).filter(Servico.id == servico_id).first()
        if not servico:
            raise HTTPException(status_code=404, detail="Serviço não encontrado")

        servico.ativo = False
