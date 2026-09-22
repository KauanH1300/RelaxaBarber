import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.models.usuario import Usuario
from app.api.deps import get_db, exigir_perfil
from app.models.usuario import PerfilEnum
from app.models.servico import Servico
from app.schemas.servico import ServicoCreate, ServicoUpdate, ServicoOut

router = APIRouter(prefix="/servicos", tags=["Serviços"])


@router.get("/", response_model=list[ServicoOut])
def listar_servicos(db: Session = Depends(get_db)):
    return db.query(Servico).filter(Servico.ativo == True).all()


@router.post("/", response_model=ServicoOut, status_code=status.HTTP_201_CREATED)
def criar_servico(
    servico: ServicoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    novo = Servico(**servico.model_dump())
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.put("/{servico_id}", response_model=ServicoOut)
def atualizar_servico(
    servico_id: uuid.UUID,
    dados: ServicoUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    servico = db.query(Servico).filter(Servico.id == servico_id).first()
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(servico, campo, valor)

    db.commit()
    db.refresh(servico)
    return servico


@router.delete("/{servico_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_servico(
    servico_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: Usuario = Depends(exigir_perfil(PerfilEnum.ADMIN)),
):
    servico = db.query(Servico).filter(Servico.id == servico_id).first()
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    servico.ativo = False
    db.commit()