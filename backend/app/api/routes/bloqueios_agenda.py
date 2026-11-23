from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response

from app.api.routes.financeiro import Banco, Ator
from app.schemas.complementos_agenda import BloqueioCreate, BloqueioOut
from app.services import bloqueios_agenda as bloqueios
from app.services.errors import FilialObrigatoria, HorarioAgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado, SemPermissao

router = APIRouter(prefix='/agendamentos/bloqueios', tags=['Bloqueios de agenda'])


def executar(operacao, *args, **kwargs):
    try:
        return operacao(*args, **kwargs)
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except RecursoNaoEncontrado as exc:
        raise HTTPException(404, str(exc), headers={'Cache-Control': 'no-store'}) from exc
    except HorarioOcupado as exc:
        raise HTTPException(409, str(exc)) from exc
    except (FilialObrigatoria, HorarioAgendamentoInvalido) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get('', response_model=list[BloqueioOut])
def listar(data: date, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    return executar(bloqueios.listar, db, usuario, filial_id, data)


@router.post('', response_model=BloqueioOut, status_code=201)
def criar(dados: BloqueioCreate, db: Banco, usuario: Ator,
          chave: Annotated[UUID | None, Header(alias='Idempotency-Key')] = None):
    return executar(bloqueios.criar, db, usuario, dados, chave)


@router.get('/cadastros/{chave}', response_model=BloqueioOut)
def conferir_criacao(chave: UUID, db: Banco, usuario: Ator, response: Response, filial_id: UUID | None = None):
    response.headers['Cache-Control'] = 'no-store'
    return executar(bloqueios.consultar, db, usuario, filial_id, chave, por_chave=True)


@router.get('/{bloqueio_id}', response_model=BloqueioOut)
def conferir_remocao(bloqueio_id: UUID, db: Banco, usuario: Ator, response: Response, filial_id: UUID | None = None):
    response.headers['Cache-Control'] = 'no-store'
    return executar(bloqueios.consultar, db, usuario, filial_id, bloqueio_id)


@router.delete('/{bloqueio_id}', status_code=204, response_class=Response)
def revogar(bloqueio_id: UUID, db: Banco, usuario: Ator, filial_id: UUID | None = None):
    executar(bloqueios.revogar, db, usuario, filial_id, bloqueio_id)
    return Response(status_code=204)
