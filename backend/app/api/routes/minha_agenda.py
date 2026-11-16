from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,Request,HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.api.routes.portal_clientes import COOKIE,origem_confiavel,executar
from app.schemas.minha_agenda import MinhaAgendaOut,OperacaoAgendaCliente,RemarcarCliente,OpcoesMinhaAgenda
from app.services import minha_agenda as service
from app.services.errors import RecursoNaoEncontrado,ConflitoEstadoAgendamento,HorarioOcupado,AgendamentoInvalido

router=APIRouter(prefix='/portal-clientes/agendamentos',tags=['Meus agendamentos'])


def chamar(func,*args):
    try:return executar(func,*args)
    except RecursoNaoEncontrado:raise HTTPException(404,'Agendamento não encontrado.') from None
    except (ConflitoEstadoAgendamento,HorarioOcupado) as e:raise HTTPException(409,str(e)) from None
    except AgendamentoInvalido:raise HTTPException(422,'Data ou horário inválido. Revise suas escolhas.') from None


@router.get('',response_model=list[MinhaAgendaOut])
def listar(request:Request,db:Session=Depends(get_db)):
    return chamar(service.listar,db,request.cookies.get(COOKIE))


@router.get('/{id_}/opcoes',response_model=OpcoesMinhaAgenda)
def opcoes(id_:UUID,request:Request,data:date|None=None,barbeiro_id:UUID|None=None,db:Session=Depends(get_db)):
    return chamar(service.opcoes,db,request.cookies.get(COOKIE),id_,data,barbeiro_id)


@router.get('/{id_}',response_model=MinhaAgendaOut)
def consultar(id_:UUID,request:Request,db:Session=Depends(get_db)):
    return chamar(service.consultar,db,request.cookies.get(COOKIE),id_)


@router.post('/{id_}/cancelamento',response_model=MinhaAgendaOut,dependencies=[Depends(origem_confiavel)])
def cancelar(id_:UUID,dados:OperacaoAgendaCliente,request:Request,db:Session=Depends(get_db)):
    return chamar(service.cancelar,db,request.cookies.get(COOKIE),id_,dados)


@router.patch('/{id_}/reagendamento',response_model=MinhaAgendaOut,dependencies=[Depends(origem_confiavel)])
def remarcar(id_:UUID,dados:RemarcarCliente,request:Request,db:Session=Depends(get_db)):
    return chamar(service.remarcar,db,request.cookies.get(COOKIE),id_,dados)
