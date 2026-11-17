from uuid import UUID
from fastapi import APIRouter
from app.api.financeiro_errors import RotaFinanceira
from app.api.routes.financeiro import Banco, Ator, Chave, RESPOSTAS
from app.schemas.itens_comanda import InclusaoServicoCreate, InclusaoServicoOut
from app.services.itens_comanda import adicionar_servico
from app.schemas.itens_comanda import PreviaAlteracaoCreate, AlteracaoItemCreate, PreviaAlteracaoOut, AlteracaoItemOut
from app.services import alteracoes_itens

router = APIRouter(prefix='/comandas', tags=['Itens de comanda'], route_class=RotaFinanceira, responses=RESPOSTAS)


@router.post('/{comanda_id}/itens/{item_id}/previa', response_model=PreviaAlteracaoOut)
def previa(comanda_id: UUID, item_id: UUID, dados: PreviaAlteracaoCreate, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return alteracoes_itens.previa(comanda_id, item_id, dados, db, usuario, filial_id)


@router.post('/{comanda_id}/itens/{item_id}/alteracoes', response_model=AlteracaoItemOut)
def alterar(comanda_id: UUID, item_id: UUID, dados: AlteracaoItemCreate, chave: Chave, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return alteracoes_itens.aplicar(comanda_id, item_id, dados, chave, db, usuario, filial_id)


@router.get('/{comanda_id}/itens/alteracoes', response_model=list[AlteracaoItemOut])
def historico(comanda_id: UUID, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return alteracoes_itens.historico(comanda_id, db, usuario, filial_id)


@router.post('/{comanda_id}/itens/servicos', response_model=InclusaoServicoOut)
def incluir(comanda_id: UUID, dados: InclusaoServicoCreate, chave: Chave, db: Banco,
            usuario: Ator, filial_id: UUID | None = None):
    """200 para inclusão e replay. Preço/descrição exclusivamente do catálogo.

    Repetir a mesma chave e payload após timeout. Replay não reinsere nem
    reprecifica, mesmo se o catálogo mudar ou a comanda for fechada depois.
    """
    return adicionar_servico(comanda_id, **dados.model_dump(), chave_idempotencia=chave,
                             db=db, usuario=usuario, filial_id=filial_id)
