from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import exigir_perfil, get_db
from app.api.routes.estoque import contexto, produto
from app.models import PerfilEnum
from app.models.estoque import ProdutoEstoque
from app.services import fotos_vitrine as fotos, reserva_publica, vitrine
from app.services.persistencia import transacao_escrita
from app.services.portal_cliente import PortalFalha

router = APIRouter(tags=['Vitrine'])
admin = exigir_perfil(PerfilEnum.ADMIN)


class ProdutoPublico(BaseModel):
    nome: str
    descricao: str | None
    foto_url: str | None
    preco: Decimal
    disponivel: bool


class PaginaProdutos(BaseModel):
    produtos: list[ProdutoPublico]
    proxima_pagina: int | None


@router.get('/publico/filiais/{filial_id}/produtos', response_model=PaginaProdutos)
def listar(filial_id: UUID, response: Response, db: Session = Depends(get_db),
           pagina: int = Query(1, ge=1, le=1000), limite: int = Query(20, ge=1, le=40)):
    try:
        filial = reserva_publica.filial_publica(db, filial_id=filial_id, exigir_expediente=False)
    except PortalFalha:
        raise HTTPException(404, 'Vitrine indisponível nesta filial') from None
    p = ProdutoEstoque
    linhas = db.execute(select(p.nome, p.descricao_vitrine, p.foto_vitrine, p.preco_venda, (p.saldo > 0))
        .where(p.filial_id == filial.id, p.venda.is_(True), p.consumo.is_(False),
               p.ativo.is_(True), p.visivel_vitrine.is_(True))
        .order_by(p.nome, p.id).offset((pagina - 1) * limite).limit(limite + 1)).all()
    response.headers['Cache-Control'] = 'public, max-age=30, s-maxage=30'
    return {'produtos': [ProdutoPublico(nome=nome, descricao=descricao, foto_url=fotos.url_publica(foto),
        preco=preco, disponivel=disponivel) for nome, descricao, foto, preco, disponivel in linhas[:limite]],
        'proxima_pagina': pagina + 1 if pagina < 1000 and len(linhas) > limite else None}


def produto_admin(db, usuario, filial_id, id, bloquear=False):
    ator, filial = contexto(db, usuario, filial_id, escrita=bloquear)
    if ator.perfil != PerfilEnum.ADMIN:
        raise HTTPException(403, 'Somente ADMIN pode editar fotos')
    return produto(db, filial, id, bloquear)


def publicar(db, usuario, filial_id, id, conteudo, mime):
    try:
        processada = fotos.processar(conteudo, mime)
        with transacao_escrita(db):
            produto_admin(db, usuario, filial_id, id)
            caminho = vitrine.preparar_upload(db)
        fotos.enviar(caminho, processada)
        with transacao_escrita(db):
            item = produto_admin(db, usuario, filial_id, id, bloquear=True)
            vitrine.trocar_foto(db, item, caminho)
    except fotos.FotoInvalida as exc:
        raise HTTPException(422, str(exc)) from exc
    except fotos.StorageIndisponivel as exc:
        raise HTTPException(503, 'Armazenamento de fotos indisponível') from exc
    return {'foto_url': fotos.url_publica(caminho)}


@router.put('/estoque/produtos/{id}/foto')
async def enviar_foto(id: UUID, request: Request, tarefas: BackgroundTasks, filial_id: UUID,
                      db: Session = Depends(get_db), usuario=Depends(admin)):
    mime = request.headers.get('content-type', '').split(';')[0].lower()
    if mime not in fotos.FORMATOS:
        raise HTTPException(415, 'Envie JPEG, PNG ou WebP')
    conteudo = bytearray()
    async for parte in request.stream():
        if len(conteudo) + len(parte) > fotos.LIMITE:
            raise HTTPException(413, 'A foto pode ter até 8 MB')
        conteudo.extend(parte)
    resultado = await run_in_threadpool(publicar, db, usuario, filial_id, id, conteudo, mime)
    tarefas.add_task(vitrine.limpar, db.get_bind())
    return resultado


@router.delete('/estoque/produtos/{id}/foto', status_code=204)
def remover_foto(id: UUID, tarefas: BackgroundTasks, filial_id: UUID,
                 db: Session = Depends(get_db), usuario=Depends(admin)):
    with transacao_escrita(db):
        item = produto_admin(db, usuario, filial_id, id, bloquear=True)
        vitrine.trocar_foto(db, item, None)
    tarefas.add_task(vitrine.limpar, db.get_bind())
    return Response(status_code=204)
