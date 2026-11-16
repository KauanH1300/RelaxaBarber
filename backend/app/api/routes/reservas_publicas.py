from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.api.deps import get_current_user
from app.api.routes.portal_clientes import COOKIE, origem_confiavel, executar
from app.schemas.reserva_publica import ReservaPublicaCreate, ReservaPublicaOut, ProfissionalPublico, HorariosPublicos, HabilitacoesUpdate
from app.services import reserva_publica as service
from app.services.errors import RecursoNaoEncontrado, SemPermissao, HorarioAgendamentoInvalido, HorarioOcupado, ValoresAgendamentoInvalidos

router=APIRouter(tags=['Agenda pública'])


def chamar(func,*args):
    try:return executar(func,*args)
    except RecursoNaoEncontrado:raise HTTPException(404,'Serviço ou profissional indisponível.') from None
    except SemPermissao:raise HTTPException(403,'Sem permissão para esta operação.') from None
    except HorarioOcupado:raise HTTPException(409,'Este horário foi ocupado ou não está mais disponível. Escolha outro horário.') from None
    except (HorarioAgendamentoInvalido,ValoresAgendamentoInvalidos):raise HTTPException(422,'Data ou horário inválido para este atendimento.') from None


@router.get('/publico/barbeiros',response_model=list[ProfissionalPublico])
def profissionais(servico_id:UUID,db:Session=Depends(get_db)):
    return chamar(service.listar_profissionais,db,servico_id)


@router.get('/publico/horarios',response_model=HorariosPublicos)
def horarios(servico_id:UUID,data:date,barbeiro_id:UUID|None=None,db:Session=Depends(get_db)):
    return chamar(service.listar_horarios,db,servico_id,data,barbeiro_id)


@router.post('/portal-clientes/reservas',response_model=ReservaPublicaOut,status_code=201,dependencies=[Depends(origem_confiavel)])
def reservar(dados:ReservaPublicaCreate,request:Request,db:Session=Depends(get_db)):
    return chamar(service.confirmar,db,dados,request.cookies.get(COOKIE))


@router.get('/portal-clientes/reservas/{chave}',response_model=ReservaPublicaOut)
def consultar(chave:UUID,request:Request,db:Session=Depends(get_db)):
    return chamar(service.consultar,db,chave,request.cookies.get(COOKIE))


@router.put('/filiais/{filial_id}/barbeiros/{barbeiro_id}/servicos')
def habilitar(filial_id:UUID,barbeiro_id:UUID,dados:HabilitacoesUpdate,db:Session=Depends(get_db),usuario=Depends(get_current_user)):
    return chamar(service.configurar_habilitacoes,db,usuario,filial_id,barbeiro_id,dados)
