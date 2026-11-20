from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response

from app.api.routes.financeiro import Banco, Ator
from app.schemas.complementos_agenda import BloqueioCreate, BloqueioOut
from app.services import bloqueios_agenda as bloqueios
from app.services.errors import FilialObrigatoria, HorarioAgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado, SemPermissao

router = APIRouter(prefix='/agendamentos/bloqueios', tags=['Bloqueios de agenda'])


def executar(operacao, *args):
    try:
        return operacao(*args)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc)) from exc
    except HorarioOcupado as exc:
        raise HTTPException(409, str(exc)) from exc
    except (FilialObrigatoria, HorarioAgendamentoInvalido) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('', response_model=list[BloqueioOut])
def listar(data: date, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return executar(bloqueios.listar, db, usuario, filial_id, data)


@router.post('', response_model=BloqueioOut, status_code=201)
def criar(dados: BloqueioCreate, db: Banco, usuario: Ator):
    return executar(bloqueios.criar, db, usuario, dados)


@router.delete('/{bloqueio_id}', status_code=204, response_class=Response)
def revogar(bloqueio_id: UUID, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    executar(bloqueios.revogar, db, usuario, filial_id, bloqueio_id)
    return Response(status_code=204)
