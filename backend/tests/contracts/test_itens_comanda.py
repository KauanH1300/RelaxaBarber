from uuid import uuid4
import pytest
from pydantic import ValidationError


@pytest.mark.parametrize('q', [0, -1, 1000, 1.5, True, '2', None])
def test_quantidade_estrita(isolated_runtime, q):
    from app.schemas.itens_comanda import InclusaoServicoCreate
    with pytest.raises(ValidationError):
        InclusaoServicoCreate(servico_id=uuid4(), quantidade=q)


def test_preco_e_descricao_nao_aceitos_no_payload(isolated_runtime):
    from app.schemas.itens_comanda import InclusaoServicoCreate
    for campo in ('preco_unitario', 'descricao', 'subtotal', 'filial_id'):
        with pytest.raises(ValidationError):
            InclusaoServicoCreate(servico_id=uuid4(), quantidade=1, **{campo: 'manipulado'})
