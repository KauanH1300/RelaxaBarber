import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.vitrine import FotoPendente
from app.services import fotos_vitrine
from app.services.persistencia import transacao_escrita

log = logging.getLogger(__name__)


def agora():
    return datetime.now(timezone.utc)


def preparar_upload(db):
    caminho = uuid4().hex + '.webp'
    db.add(FotoPendente(caminho=caminho, remover_apos=agora() + timedelta(minutes=15)))
    return caminho


def trocar_foto(db, produto, caminho):
    anterior = produto.foto_vitrine
    if caminho:
        reserva = db.execute(delete(FotoPendente).where(
            FotoPendente.caminho == caminho, FotoPendente.remover_apos > agora(),
        ).returning(FotoPendente.caminho)).scalar_one_or_none()
        if not reserva:
            raise fotos_vitrine.StorageIndisponivel()
    produto.foto_vitrine = caminho
    if anterior:
        db.add(FotoPendente(caminho=anterior, remover_apos=agora()))


def limpar(bind):
    try:
        with Session(bind) as db, transacao_escrita(db):
            fotos = list(db.scalars(select(FotoPendente).where(FotoPendente.remover_apos <= agora())
                .order_by(FotoPendente.remover_apos, FotoPendente.caminho)
                .limit(25).with_for_update(skip_locked=True)))
            if not fotos:
                return
            try:
                fotos_vitrine.apagar([foto.caminho for foto in fotos])
            except fotos_vitrine.StorageIndisponivel:
                for foto in fotos:
                    foto.remover_apos = agora() + timedelta(minutes=1)
                log.warning('Exclusão de fotos adiada pelo Storage')
            else:
                for foto in fotos:
                    db.delete(foto)
    except Exception:
        log.error('Falha ao processar a fila de exclusão de fotos')


@asynccontextmanager
async def ciclo_storage(app):
    if not fotos_vitrine.pronto():
        yield
        return
    from app.db.database import engine

    parar = asyncio.Event()

    async def executar():
        while not parar.is_set():
            await asyncio.to_thread(limpar, engine)
            try:
                await asyncio.wait_for(parar.wait(), timeout=60)
            except TimeoutError:
                continue

    tarefa = asyncio.create_task(executar())
    try:
        yield
    finally:
        parar.set()
        await tarefa
