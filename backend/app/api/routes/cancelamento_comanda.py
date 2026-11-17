from uuid import UUID
from fastapi import APIRouter
from app.api.financeiro_errors import RotaFinanceira
from app.api.routes.financeiro import Banco, Ator, Chave, RESPOSTAS
from app.schemas.cancelamento_comanda import CancelamentoComandaCreate, CancelamentoComandaOut
from app.services.cancelamento_comanda import cancelar

router = APIRouter(prefix='/comandas', tags=['Cancelamento de comandas'], route_class=RotaFinanceira, responses=RESPOSTAS)


@router.post('/{comanda_id}/cancelamento', response_model=CancelamentoComandaOut)
def cancelar_comanda(comanda_id: UUID, dados: CancelamentoComandaCreate, chave: Chave,
                     db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return cancelar(comanda_id, dados, chave, db, usuario, filial_id)
