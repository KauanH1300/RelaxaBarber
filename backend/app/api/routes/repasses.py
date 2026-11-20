from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field
from app.api.financeiro_errors import RotaFinanceira
from app.api.routes.financeiro import Ator, Banco, Chave
from app.services import repasses

router=APIRouter(prefix='/repasses',tags=['Repasses de comissão'],route_class=RotaFinanceira)

class Periodo(BaseModel):
    model_config=ConfigDict(extra='forbid')
    inicio: date
    fim: date

class Pagamento(BaseModel):
    model_config=ConfigDict(extra='forbid')
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    metodo: Literal['pix','dinheiro','transferencia']
    data_pagamento: datetime

class Estorno(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    valor: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    motivo: str = Field(min_length=1,max_length=1000)

@router.get('/profissionais/{profissional_id}')
def consultar(profissional_id: UUID,filial_id: UUID,inicio: date,fim: date,db: Banco,usuario: Ator):
    return repasses.consultar(db,usuario,filial_id,profissional_id,inicio,fim)

@router.get('/profissionais/{profissional_id}/operacao')
def conferir(profissional_id: UUID, filial_id: UUID, chave: Chave, db: Banco, usuario: Ator,
             response: Response, fechamento_id: UUID | None = None, pagamento_id: UUID | None = None):
    response.headers['Cache-Control'] = 'no-store'
    return repasses.conferir(db, usuario, filial_id, profissional_id, chave, fechamento_id, pagamento_id)

@router.post('/profissionais/{profissional_id}/fechamentos',status_code=201)
def fechar(profissional_id: UUID,filial_id: UUID,dados: Periodo,chave: Chave,db: Banco,usuario: Ator):
    return repasses.fechar(db,usuario,filial_id,profissional_id,dados.inicio,dados.fim,chave)

@router.post('/profissionais/{profissional_id}/fechamentos/{fechamento_id}/pagamentos',status_code=201)
def pagar(profissional_id: UUID,fechamento_id: UUID,filial_id: UUID,dados: Pagamento,chave: Chave,db: Banco,usuario: Ator):
    return repasses.pagar(db,usuario,filial_id,profissional_id,fechamento_id,dados.valor,dados.metodo,dados.data_pagamento,chave)

@router.post('/profissionais/{profissional_id}/fechamentos/{fechamento_id}/pagamentos/{pagamento_id}/estornos',status_code=201)
def estornar(profissional_id: UUID,fechamento_id: UUID,pagamento_id: UUID,filial_id: UUID,dados: Estorno,chave: Chave,db: Banco,usuario: Ator):
    return repasses.estornar(db,usuario,filial_id,profissional_id,fechamento_id,pagamento_id,dados.valor,dados.motivo,chave)
