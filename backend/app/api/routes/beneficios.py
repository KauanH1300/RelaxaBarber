from uuid import UUID
from fastapi import APIRouter
from app.api.financeiro_errors import RotaFinanceira
from app.api.routes.financeiro import Banco, Ator, Chave, RESPOSTAS
from app.schemas.beneficios import BeneficioPreviaCreate, BeneficioCreate, BeneficioPreviaOut, BeneficioOut
from app.services import beneficios

router = APIRouter(prefix='/comandas', tags=['Descontos e cortesias'], route_class=RotaFinanceira, responses=RESPOSTAS)


@router.post('/{comanda_id}/beneficios/previa', response_model=BeneficioPreviaOut)
def previa(comanda_id: UUID, dados: BeneficioPreviaCreate, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return beneficios.previa(comanda_id, dados, db, usuario, filial_id)


@router.post('/{comanda_id}/beneficios', response_model=BeneficioOut)
def aplicar(comanda_id: UUID, dados: BeneficioCreate, chave: Chave, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return beneficios.aplicar(comanda_id, dados, chave, db, usuario, filial_id)


@router.get('/{comanda_id}/beneficios', response_model=list[BeneficioOut])
def historico(comanda_id: UUID, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return beneficios.historico(comanda_id, db, usuario, filial_id)
