from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.cliente import Cliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteOut

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


@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def criar_cliente(dados: ClienteCreate, db: Session = Depends(get_db)):
    _checar_duplicado(db, dados.telefone, dados.email)
    cliente = Cliente(nome=dados.nome, telefone=dados.telefone, email=dados.email)
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.get("", response_model=list[ClienteOut])
def listar_clientes(busca: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(Cliente).filter(Cliente.ativo == True)
    if busca:
        termo = f"%{busca}%"
        q = q.filter(or_(Cliente.nome.ilike(termo), Cliente.telefone.ilike(termo)))
    return q.order_by(Cliente.nome).all()


@router.get("/{cliente_id}", response_model=ClienteOut)
def buscar_cliente(cliente_id: UUID, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    return cliente


@router.patch("/{cliente_id}", response_model=ClienteOut)
def editar_cliente(cliente_id: UUID, dados: ClienteUpdate, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")

    campos = dados.model_dump(exclude_unset=True)
    _checar_duplicado(db, campos.get("telefone"), campos.get("email"), ignorar_id=cliente.id)
    for campo, valor in campos.items():
        setattr(cliente, campo, valor)

    db.commit()
    db.refresh(cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def desativar_cliente(cliente_id: UUID, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    cliente.ativo = False  # não apaga: preserva o histórico de agendamentos
    db.commit()