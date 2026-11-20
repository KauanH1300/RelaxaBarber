"""Recuperação da equipe com limitação persistida e entrega pós-resposta."""
import hmac
import logging
import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.core.security import hash_senha
from app.models.sessao_equipe import RecuperacaoEquipe
from app.models.usuario import Usuario
from app.services import entrega_codigo_cliente as entrega, sessoes_equipe
from app.services.persistencia import transacao_escrita
from app.services.portal_cliente import _bucket, agora, segredo, utc

log = logging.getLogger(__name__)
MENSAGEM = 'Se o pedido for elegível, use o código enviado ao e-mail informado.'
CODIGO_INVALIDO = 'Código inválido, expirado ou pedido indisponível. Solicite outro código.'


def admitir(db, email, ip):
    with transacao_escrita(db):
        # A admissão não consulta a conta nem acessa SMTP.
        return (_bucket(db, 'equipe:codigo:ip:' + ip, 10, 3600)
                and _bucket(db, 'equipe:codigo:email:' + email, 5, 3600, 60))


def hash_codigo(id_, codigo):
    return segredo('equipe-codigo', f'{id_}:{codigo}')


def invalidar_codigos(db, usuario_id):
    instante = agora()
    db.execute(update(RecuperacaoEquipe).where(
        RecuperacaoEquipe.usuario_id == usuario_id, RecuperacaoEquipe.consumida_em.is_(None),
        RecuperacaoEquipe.expira_em > instante,
    ).values(consumida_em=instante))


def enviar_codigo(engine, id_, email):
    try:
        with Session(engine) as db:
            codigo = f'{secrets.randbelow(1000000):06d}'
            with transacao_escrita(db):
                candidatos = db.scalars(select(Usuario).where(func.lower(Usuario.email) == email)
                    .order_by(Usuario.id).limit(2).with_for_update().execution_options(populate_existing=True)).all()
                if len(candidatos) != 1 or not candidatos[0].ativo:
                    return
                usuario = candidatos[0]
                instante = agora()
                db.execute(delete(RecuperacaoEquipe).where(RecuperacaoEquipe.expira_em <= instante))
                invalidar_codigos(db, usuario.id)
                db.add(RecuperacaoEquipe(
                    id=id_, usuario_id=usuario.id, codigo_hash=hash_codigo(id_, codigo),
                    credencial_hash=segredo('equipe-credencial', usuario.senha_hash),
                    expira_em=instante + timedelta(minutes=10),
                ))
            try:
                entrega.enviar(email, codigo)
            except entrega.EntregaIndisponivel:
                with transacao_escrita(db):
                    db.execute(update(RecuperacaoEquipe).where(
                        RecuperacaoEquipe.id == id_, RecuperacaoEquipe.consumida_em.is_(None),
                    ).values(consumida_em=agora()))
                log.warning('Falha no envio do código de recuperação da equipe')
    except Exception:
        # O HTTP já foi enviado. Não registrar e-mail, código ou parâmetros SQL.
        log.error('Falha ao processar recuperação da equipe')


def alterar_senha(db, usuario, senha):
    usuario.senha_hash = hash_senha(senha)
    invalidar_codigos(db, usuario.id)
    sessoes_equipe.revogar_todas(db, usuario.id)


def redefinir(db, dados, ip):
    with transacao_escrita(db):
        if not _bucket(db, 'equipe:confirmacao:ip:' + ip, 30, 3600):
            return False
        usuario_id = db.scalar(select(RecuperacaoEquipe.usuario_id).where(
            RecuperacaoEquipe.id == dados.solicitacao_id,
        ))
        if usuario_id is None:
            return False
        usuario = db.scalar(select(Usuario).where(Usuario.id == usuario_id)
                            .with_for_update().execution_options(populate_existing=True))
        pedido = db.scalar(select(RecuperacaoEquipe).where(RecuperacaoEquipe.id == dados.solicitacao_id)
                           .with_for_update().execution_options(populate_existing=True))
        if not pedido or pedido.consumida_em is not None or utc(pedido.expira_em) <= agora():
            return False
        pedido.tentativas += 1
        correto = hmac.compare_digest(pedido.codigo_hash, hash_codigo(pedido.id, dados.codigo))
        elegivel = usuario and usuario.ativo and hmac.compare_digest(
            pedido.credencial_hash, segredo('equipe-credencial', usuario.senha_hash),
        )
        if correto or pedido.tentativas >= 5:
            pedido.consumida_em = agora()
        if not correto or not elegivel:
            return False
        alterar_senha(db, usuario, dados.senha)
        return True
