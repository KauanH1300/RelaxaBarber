import uuid
from typing import Annotated
from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.api.deps import get_db, exigir_perfil, get_current_user
from app.models.usuario import PerfilEnum
from app.models.servico import Servico
from app.schemas.servico import ServicoCreate, ServicoUpdate, ServicoOut, ServicoCatalogoOut

from app.services.persistencia import transacao_escrita, recarregar_confirmado

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
            for servico in db.query(Servico).filter(Servico.ativo == True).all()]


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
                      usuario=Depends(exigir_perfil(PerfilEnum.ADMIN))):
    try:
        filial = filiais.resolver_filial(db, usuario, filial_id)
        return insumos_servico.listar(db, servico_id, filial.id)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put('/{servico_id}/insumos', response_model=list[InsumoPadrao])
def salvar_insumos(servico_id: uuid.UUID, filial_id: uuid.UUID,
                   itens: Annotated[list[InsumoPadrao], Body(max_length=100)], db: Session = Depends(get_db),
                   usuario=Depends(exigir_perfil(PerfilEnum.ADMIN))):
    try:
        with transacao_escrita(db):
            atual = filiais.usuario_atual(db, usuario, bloquear=True)
            if atual.perfil != PerfilEnum.ADMIN:
                raise SemPermissao('Somente ADMIN pode configurar insumos')
            filial = filiais.resolver_filial(db, atual, filial_id, bloquear=True)
            insumos_servico.configurar(db, servico_id, filial.id, itens)
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
):
    with transacao_escrita(db):
        novo = Servico(**servico.model_dump())
        db.add(novo)
    recarregar_confirmado(db, novo)
    return novo


@router.put("/{servico_id}", response_model=ServicoOut)
def atualizar_servico(
    servico_id: uuid.UUID,
    dados: ServicoUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    with transacao_escrita(db):
        servico = db.query(Servico).filter(Servico.id == servico_id).first()
        if not servico:
            raise HTTPException(status_code=404, detail="Serviço não encontrado")

        for campo, valor in dados.model_dump(exclude_unset=True).items():
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
