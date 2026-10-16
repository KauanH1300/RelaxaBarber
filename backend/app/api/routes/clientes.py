from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, exigir_perfil
from app.models.usuario import PerfilEnum, Usuario
from app.db.database import get_db
from app.models.cliente import Cliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteOut, ClientePesquisaOut

from app.services import filiais, clientes as clientes_service
from app.services.errors import SemPermissao, FilialObrigatoria, RecursoNaoEncontrado
from app.services.resumo_cliente import consultar_resumo
from app.schemas.resumo_cliente import ResumoCliente, ResumoFinanceiroCliente
from app.services.persistencia import transacao_escrita, recarregar_confirmado

router = APIRouter(
    prefix="/clientes",
    tags=["Clientes"],
    dependencies=[Depends(get_current_user)],  # todas as rotas exigem login
)


def _checar_duplicado(db: Session, telefone: Optional[str], email: Optional[str], ignorar_id: Optional[UUID] = None):
    if telefone:
        q = db.query(Cliente).filter(Cliente.telefone == telefone)
        if ignorar_id:
            q = q.filter(Cliente.id != ignorar_id)
        if q.first():
            raise HTTPException(409, "Já existe um cliente com esse telefone")
    if email:
        q = db.query(Cliente).filter(Cliente.email == email)
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


@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def criar_cliente(dados: ClienteCreate, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    with transacao_escrita(db):
        filial = _resolver_filial(db, usuario, dados.filial_id, bloquear=True)
        _checar_duplicado(db, dados.telefone, dados.email)
        cliente = Cliente(nome=dados.nome, telefone=dados.telefone, email=dados.email)
        db.add(cliente)
        db.flush()
        clientes_service.garantir_vinculo(db, cliente.id, filial.id)
    recarregar_confirmado(db, cliente)
    return cliente


@router.get("", response_model=list[ClienteOut])
def listar_clientes(busca: Optional[str] = None, db: Session = Depends(get_db),
                    usuario=Depends(get_current_user), filial_id: UUID | None = None):
    filial = _resolver_filial(db, usuario, filial_id)
    query = clientes_service.consulta_local(db, filial.id).filter(Cliente.ativo.is_(True))
    return clientes_service.filtrar_busca(query, busca).all()


# Rota estática precisa preceder /{cliente_id}.
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
    """ADMIN apenas. Sem pagamentos implementados, todos os valores são null."""
    return _resumo(db, usuario, cliente_id, filial_id, financeiro=True)


@router.get("/{cliente_id}", response_model=ClienteOut)
def buscar_cliente(cliente_id: UUID, db: Session = Depends(get_db),
                   usuario=Depends(get_current_user), filial_id: UUID | None = None):
    filial = _resolver_filial(db, usuario, filial_id)
    cliente = clientes_service.consulta_local(db, filial.id).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    return cliente


@router.patch("/{cliente_id}", response_model=ClienteOut)
def editar_cliente(cliente_id: UUID, dados: ClienteUpdate, db: Session = Depends(get_db),
                   usuario=Depends(get_current_user), filial_id: UUID | None = None):
    with transacao_escrita(db):
        filial = _resolver_filial(db, usuario, filial_id, bloquear=True)
        cliente = clientes_service.consulta_local(db, filial.id).populate_existing().with_for_update(of=Cliente).filter(Cliente.id == cliente_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente não encontrado")
        campos = dados.model_dump(exclude_unset=True)
        _checar_duplicado(db, campos.get("telefone"), campos.get("email"), ignorar_id=cliente.id)
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
