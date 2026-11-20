"""Sessões da equipe. Somente hashes dos identificadores são persistidos."""
from uuid import uuid4

from sqlalchemy import delete, select, update

from app.core.security import criar_token, ler_token
from app.models.sessao_equipe import SessaoEquipe
from app.models.usuario import Usuario
from app.services.portal_cliente import agora, segredo


def chave_sessao(jti):
    return segredo('equipe-jti', str(jti))


def emitir(db, usuario_id):
    from app.core.security import expira_token

    jti, expira = uuid4(), expira_token()
    db.execute(delete(SessaoEquipe).where(SessaoEquipe.expira_em <= agora()))
    db.add(SessaoEquipe(jti_hash=chave_sessao(jti), usuario_id=usuario_id, expira_em=expira))
    return criar_token(usuario_id, jti, expira)


def validar(db, token):
    credencial = ler_token(token)
    if credencial is None:
        return None
    usuario_id, jti = credencial
    return db.scalar(select(Usuario).join(SessaoEquipe, SessaoEquipe.usuario_id == Usuario.id).where(
        Usuario.id == usuario_id, Usuario.ativo.is_(True), SessaoEquipe.jti_hash == chave_sessao(jti),
        SessaoEquipe.revogada_em.is_(None), SessaoEquipe.expira_em > agora(),
    ).execution_options(populate_existing=True))


def revogar(db, token, usuario_id):
    credencial = ler_token(token)
    if credencial is None:
        return
    _, jti = credencial
    db.execute(update(SessaoEquipe).where(
        SessaoEquipe.jti_hash == chave_sessao(jti), SessaoEquipe.usuario_id == usuario_id,
        SessaoEquipe.revogada_em.is_(None),
    ).values(revogada_em=agora()))


def revogar_todas(db, usuario_id):
    instante = agora()
    db.execute(update(SessaoEquipe).where(
        SessaoEquipe.usuario_id == usuario_id, SessaoEquipe.revogada_em.is_(None),
        SessaoEquipe.expira_em > instante,
    ).values(revogada_em=instante))
