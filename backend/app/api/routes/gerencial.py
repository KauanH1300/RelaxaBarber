"""Dashboard, relatórios e trilhas de auditoria exclusivos da administração."""
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.financeiro_errors import RotaFinanceira
from app.api.routes.financeiro import Ator, Banco
from app.services import gerencial, gerencial_historico

router = APIRouter(prefix='/gerencial', tags=['Gerencial'], route_class=RotaFinanceira)


@router.get('/resumo')
def resumo(
    db: Banco, usuario: Ator, filial_id: UUID, inicio: date, fim: date,
    profissional_id: UUID | None = None, granularidade: Literal['dia', 'semana', 'mes'] = 'dia',
    busca: str = Query('', max_length=100), ordem: Literal['quantidade', 'faturado'] = 'quantidade',
    ordem_equipe: Literal['concluidos', 'faturado', 'recebido_liquido', 'liberada'] = 'faturado',
    formato: Literal['json', 'csv'] = 'json',
):
    filial = gerencial.contexto(db, usuario, filial_id, inicio, fim)
    dados = gerencial.consultar(db, filial, inicio, fim, profissional_id, granularidade, busca, ordem, ordem_equipe)
    if formato == 'csv':
        arquivo = gerencial.exportar(dados, filial=filial, inicio=inicio, fim=fim, profissional_id=profissional_id,
                                    granularidade=granularidade, busca=busca, ordem=ordem, ordem_equipe=ordem_equipe)
        return Response(arquivo, media_type='text/csv',
                        headers={'Content-Disposition': 'attachment; filename="relatorio-gerencial.csv"',
                                 'Cache-Control': 'no-store'})
    return JSONResponse(jsonable_encoder(dados, custom_encoder={Decimal: str}), headers={'Cache-Control': 'no-store'})


@router.get('/historico')
def historico(
    db: Banco, usuario: Ator, filial_id: UUID, inicio: date, fim: date,
    tipo: str | None = None, pagina: int = Query(1, ge=1, le=1_000_000), tamanho: int = Query(25, ge=1, le=100),
):
    filial = gerencial.contexto(db, usuario, filial_id, inicio, fim)
    if tipo is not None and tipo not in gerencial_historico.FONTES:
        raise HTTPException(422, 'Tipo de evento inválido')
    dados = gerencial_historico.consultar(db, filial, inicio, fim, tipo, pagina, tamanho)
    return JSONResponse(jsonable_encoder(dados), headers={'Cache-Control': 'no-store'})

