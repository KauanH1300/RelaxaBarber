from typing import Annotated, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, exigir_perfil
from app.models.usuario import PerfilEnum, Usuario
from app.db.database import get_db
from app.models.cliente import Cliente
from app.models.portal_cliente import ContaPortalCliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteListaOut, ClientePerfilOut, ClientePesquisaOut, GrupoDuplicidadeOut

from app.services import filiais, clientes as clientes_service
from app.services.errors import SemPermissao, FilialObrigatoria, RecursoNaoEncontrado
from app.services.resumo_cliente import consultar_resumo
from app.services import linha_tempo_cliente
from app.schemas.linha_tempo_cliente import PaginaAtendimentos
from app.schemas.resumo_cliente import ResumoCliente, ResumoFinanceiroCliente
from app.services.persistencia import transacao_escrita, recarregar_confirmado
from app.services.cadastro_idempotente import id_cadastro, travar_cadastro

router = APIRouter(
    prefix="/clientes",
    tags=["Clientes"],
    dependencies=[Depends(get_current_user)],  # todas as rotas exigem login
)


def _checar_email_contato(db: Session, email: Optional[str], ignorar_id: Optional[UUID] = None):
    if email:
        q = db.query(Cliente).filter(Cliente.email == email, Cliente.conta_ativada.is_(False))
        if ignorar_id:
            q = q.filter(Cliente.id != ignorar_id)
        if q.first():
            raise HTTPException(409, "Já existe um cliente com esse e-mail")


def _resolver_filial(db, usuario, filial_id=None, bloquear=False):
    try:
        return filiais.resolver_filial(db, usuario, filial_id, bloquear=bloquear)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("", response_model=ClientePerfilOut, status_code=status.HTTP_201_CREATED)
def criar_cliente(dados: ClienteCreate, db: Session = Depends(get_db), usuario=Depends(get_current_user),
                  chave: Annotated[UUID | None, Header(alias='Idempotency-Key')] = None):
    with transacao_escrita(db):
        filial = _resolver_filial(db, usuario, dados.filial_id, bloquear=True)
        ident = id_cadastro('cliente', usuario.id, chave, filial.id) if chave else None
        if ident:
            travar_cadastro(db, ident)
            anterior = clientes_service.consulta_local(db, filial.id).filter(Cliente.id == ident).first()
            if anterior is not None:
                return anterior
        _checar_email_contato(db, dados.email)
        cliente = Cliente(id=ident, **dados.model_dump(exclude={'filial_id'}))
        db.add(cliente)
        db.flush()
        clientes_service.garantir_vinculo(db, cliente.id, filial.id)
    recarregar_confirmado(db, cliente)
    return cliente


@router.get('/cadastros/{chave}', response_model=ClientePerfilOut)
def conferir_cadastro(chave: UUID, db: Session = Depends(get_db), usuario=Depends(get_current_user),
                      filial_id: UUID | None = None):
    filial = _resolver_filial(db, usuario, filial_id)
    return buscar_cliente(id_cadastro('cliente', usuario.id, chave, filial.id), db, usuario, filial.id)


@router.get("", response_model=list[ClienteListaOut])
def listar_clientes(busca: Optional[str] = None, db: Session = Depends(get_db),
                    usuario=Depends(get_current_user), filial_id: UUID | None = None):
    filial = _resolver_filial(db, usuario, filial_id)
    query = clientes_service.consulta_local(db, filial.id).filter(Cliente.ativo.is_(True))
    query = clientes_service.filtrar_busca(query, busca, normalizar_telefone=True)
    if usuario.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
        return query.all()
    registros = query.add_columns(clientes_service.possivel_duplicidade(filial.id)).all()
    return [ClienteListaOut.model_validate(cliente).model_copy(update={'possivel_duplicidade': duplicado})
            for cliente, duplicado in registros]


# Rota estática precisa preceder /{cliente_id}.
@router.get('/coincidencias', response_model=list[ClientePesquisaOut])
def coincidencias_telefone(
    telefone: Annotated[str, Query(min_length=1, max_length=20)],
    db: Session = Depends(get_db), usuario=Depends(get_current_user),
    filial_id: UUID | None = None, ignorar_id: UUID | None = None,
):
    filial = _resolver_filial(db, usuario, filial_id)
    return clientes_service.coincidencias_por_telefone(db, filial.id, telefone, ignorar_id)


@router.get('/duplicidades', response_model=list[GrupoDuplicidadeOut])
def listar_duplicidades(
    db: Session = Depends(get_db),
    usuario=Depends(exigir_perfil(PerfilEnum.ADMIN, PerfilEnum.RECEPCAO)),
    filial_id: UUID | None = None,
):
    filial = _resolver_filial(db, usuario, filial_id)
    return clientes_service.grupos_duplicidade(db, filial.id)


@router.get("/pesquisa", response_model=list[ClientePesquisaOut])
def pesquisar_clientes(busca: Optional[str] = None, db: Session = Depends(get_db),
                       usuario=Depends(get_current_user), filial_id: UUID | None = None):
    if filial_id is not None:
        _resolver_filial(db, usuario, filial_id)
    else:
        try:
            # Pesquisa é global: não exige escolher entre várias unidades válidas.
            if not filiais.listar_filiais(db, usuario):
                raise SemPermissao("Sem acesso a uma filial ativa")
        except SemPermissao as exc:
            raise HTTPException(403, str(exc)) from exc
    query = db.query(Cliente).filter(Cliente.ativo.is_(True))
    return clientes_service.filtrar_busca(query, busca).all()


def _resumo(db, usuario, cliente_id, filial_id, financeiro=False):
    try:
        return consultar_resumo(db, usuario, cliente_id, filial_id, financeiro=financeiro)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('/{cliente_id}/resumo', response_model=ResumoCliente)
def resumo_cliente(cliente_id: UUID, db: Session = Depends(get_db),
                   usuario=Depends(get_current_user), filial_id: UUID | None = None):
    """Contagens autorizadas; filial_id valida a abertura, não filtra o consolidado."""
    return _resumo(db, usuario, cliente_id, filial_id)


@router.get('/{cliente_id}/resumo-financeiro', response_model=ResumoFinanceiroCliente)
def resumo_financeiro(cliente_id: UUID, db: Session = Depends(get_db),
                      usuario=Depends(get_current_user), filial_id: UUID | None = None):
    """ADMIN apenas. Recebimentos líquidos dos estornos, por filial e comanda."""
    return _resumo(db, usuario, cliente_id, filial_id, financeiro=True)


@router.get('/{cliente_id}/atendimentos', response_model=PaginaAtendimentos)
def listar_atendimentos(cliente_id: UUID, filial_id: UUID, db: Session = Depends(get_db),
                       usuario=Depends(get_current_user), pagina: int = Query(1, ge=1, le=1_000_000),
                       tamanho: int = Query(10, ge=1, le=40), incluir_ocorrencias: bool = False):
    try:
        return linha_tempo_cliente.consultar(db, usuario, cliente_id, filial_id, pagina, tamanho, incluir_ocorrencias)
    except (SemPermissao, FilialObrigatoria) as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{cliente_id}", response_model=ClientePerfilOut)
def buscar_cliente(cliente_id: UUID, db: Session = Depends(get_db),
                   usuario=Depends(get_current_user), filial_id: UUID | None = None):
    filial = _resolver_filial(db, usuario, filial_id)
    cliente = clientes_service.consulta_local(db, filial.id).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    return cliente


@router.patch("/{cliente_id}", response_model=ClientePerfilOut)
def editar_cliente(cliente_id: UUID, dados: ClienteUpdate, db: Session = Depends(get_db),
                   usuario=Depends(get_current_user), filial_id: UUID | None = None):
    with transacao_escrita(db):
        filial = _resolver_filial(db, usuario, filial_id, bloquear=True)
        cliente = clientes_service.consulta_local(db, filial.id).populate_existing().with_for_update(of=Cliente).filter(Cliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        campos = dados.model_dump(exclude_unset=True)
        if 'email' in campos and campos['email'] != cliente.email:
            if db.get(ContaPortalCliente, cliente.id):
                raise HTTPException(409, 'Esta conta possui e-mail confirmado. Utilize a troca segura de e-mail no portal do cliente.')
            _checar_email_contato(db, campos['email'], ignorar_id=cliente.id)
        for campo, valor in campos.items():
            setattr(cliente, campo, valor)
    recarregar_confirmado(db, cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def desativar_cliente(cliente_id: UUID, db: Session = Depends(get_db), _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN))):
    with transacao_escrita(db):
        try:
            atual = filiais.usuario_atual(db, _, bloquear=True)
            if atual.perfil != PerfilEnum.ADMIN:
                raise SemPermissao("Sem permissão")
        except SemPermissao as exc:
            raise HTTPException(403, str(exc)) from exc
        cliente = db.query(Cliente).populate_existing().with_for_update().filter(Cliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        cliente.ativo = False  # não apaga: preserva o histórico de agendamentos
