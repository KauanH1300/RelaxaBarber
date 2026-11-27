"""Desafios restritos e dispositivos confiáveis do login administrativo."""
import hmac
import secrets
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, select, update

from app.models.sessao_equipe import DispositivoEquipe, RecuperacaoEquipe
from app.models.usuario import PerfilEnum, Usuario
from app.services import entrega_codigo_cliente as entrega, recuperacao_equipe as codigos, sessoes_equipe
from app.services.persistencia import transacao_escrita
from app.services.portal_cliente import _bucket, agora, segredo, utc

FINALIDADE = 'login_admin'
VALIDADE = 300
REENVIO = 60
PRAZO_LOGIN = 900
PRAZO_DISPOSITIVO = 30 * 86400


def _admitir_envio(db, usuario_id, ip):
    return (_bucket(db, f'equipe:login-admin:envio:ip:{ip}', 15, 3600)
            and _bucket(db, f'equipe:login-admin:envio:usuario:{usuario_id}', 5, 3600, REENVIO))


def _codigo():
    return f'{secrets.randbelow(1000000):06d}'


def iniciar(db, usuario, ip):
    if not _admitir_envio(db, usuario.id, ip):
        return None
    token, id_, codigo = secrets.token_urlsafe(32), uuid4(), _codigo()
    codigos.registrar_codigo(
        db, usuario, id_, codigo, FINALIDADE, minutos=5,
        login_token_hash=segredo('equipe-login-pendente', token),
        login_ate=agora() + timedelta(seconds=PRAZO_LOGIN),
    )
    return token, id_, usuario.email, codigo


def entregar(db, id_, email, codigo):
    filtro = (
        RecuperacaoEquipe.id == id_, RecuperacaoEquipe.finalidade == FINALIDADE,
        RecuperacaoEquipe.codigo_hash == codigos.hash_codigo(id_, codigo),
        RecuperacaoEquipe.consumida_em.is_(None),
    )
    try:
        entrega.enviar(email, codigo)
    except entrega.EntregaIndisponivel:
        with transacao_escrita(db):
            db.execute(update(RecuperacaoEquipe).where(*filtro).values(consumida_em=agora()))
        raise
    with transacao_escrita(db):
        return bool(db.execute(update(RecuperacaoEquipe).where(
            *filtro, RecuperacaoEquipe.expira_em > agora(),
        ).values(login_enviado_em=agora())).rowcount)


def _bloquear_pedido(db, token):
    if not token or len(token) > 64:
        return None, None
    filtro = (
        RecuperacaoEquipe.login_token_hash == segredo('equipe-login-pendente', token),
        RecuperacaoEquipe.finalidade == FINALIDADE,
    )
    usuario_id = db.scalar(select(RecuperacaoEquipe.usuario_id).where(*filtro))
    if usuario_id is None:
        return None, None
    usuario = db.scalar(select(Usuario).where(Usuario.id == usuario_id)
                        .with_for_update().execution_options(populate_existing=True))
    pedido = db.scalar(select(RecuperacaoEquipe).where(*filtro)
                       .with_for_update().execution_options(populate_existing=True))
    if (not usuario or not usuario.ativo or usuario.perfil != PerfilEnum.ADMIN or not pedido
            or pedido.consumida_em is not None or utc(pedido.login_ate) <= agora()
            or not hmac.compare_digest(pedido.credencial_hash, codigos.credencial(usuario))):
        return None, None
    return usuario, pedido


def reenviar(db, token, ip):
    with transacao_escrita(db):
        usuario, pedido = _bloquear_pedido(db, token)
        if pedido is None:
            return 400, None
        instante = agora()
        if utc(pedido.login_ate) - instante < timedelta(seconds=VALIDADE):
            return 400, None
        if pedido.login_enviado_em is None or not _admitir_envio(db, usuario.id, ip):
            return 429, None
        codigo = _codigo()
        while hmac.compare_digest(pedido.codigo_hash, codigos.hash_codigo(pedido.id, codigo)):
            codigo = _codigo()
        pedido.codigo_hash = codigos.hash_codigo(pedido.id, codigo)
        pedido.expira_em = instante + timedelta(seconds=VALIDADE)
        pedido.login_enviado_em = None
        return 200, (pedido.id, usuario.email, codigo)


def verificar(db, token, codigo, confiar, ip):
    with transacao_escrita(db):
        if not _bucket(db, f'equipe:login-admin:tentativas:ip:{ip}', 30, 3600):
            return 429, None, None
        usuario, pedido = _bloquear_pedido(db, token)
        if pedido is None or pedido.login_enviado_em is None or not codigos.consumir_codigo(pedido, codigo):
            return 400, None, None
        if usuario.email_confirmado_em is None:
            usuario.email_confirmado_em = agora()
        dispositivo = _cadastrar_dispositivo(db, usuario) if confiar else None
        return 200, sessoes_equipe.emitir(db, usuario.id, admin_verificado=True), dispositivo


def _dispositivos_ativos(usuario):
    return (
        DispositivoEquipe.usuario_id == usuario.id,
        DispositivoEquipe.expira_em > agora(),
        DispositivoEquipe.credencial_hash == codigos.credencial(usuario),
    )


def _cadastrar_dispositivo(db, usuario):
    token = secrets.token_urlsafe(32)
    instante = agora()
    db.execute(delete(DispositivoEquipe).where(
        DispositivoEquipe.usuario_id == usuario.id, DispositivoEquipe.expira_em <= instante,
    ))
    db.add(DispositivoEquipe(
        id=uuid4(), usuario_id=usuario.id, token_hash=segredo('equipe-dispositivo', token),
        credencial_hash=codigos.credencial(usuario), criado_em=instante,
        expira_em=instante + timedelta(seconds=PRAZO_DISPOSITIVO),
    ))
    return token


def dispositivo_valido(db, usuario, token):
    return bool(usuario.email_confirmado_em and token and len(token) <= 64 and db.scalar(
        select(DispositivoEquipe.id).where(
            *_dispositivos_ativos(usuario), DispositivoEquipe.token_hash == segredo('equipe-dispositivo', token),
        ),
    ))


def listar_dispositivos(db, usuario, token):
    atual = segredo('equipe-dispositivo', token) if token else ''
    dispositivos = db.scalars(select(DispositivoEquipe).where(*_dispositivos_ativos(usuario))
                              .order_by(DispositivoEquipe.criado_em.desc())).all()
    return [
        dict(id=item.id, criado_em=item.criado_em, expira_em=item.expira_em,
             atual=hmac.compare_digest(item.token_hash, atual))
        for item in dispositivos
    ]


def revogar_dispositivos(db, usuario_id, sessao, token, id_=None):
    with transacao_escrita(db):
        db.scalar(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update())
        usuario = sessoes_equipe.validar(db, sessao)
        if not usuario or usuario.perfil != PerfilEnum.ADMIN or not usuario.email_confirmado_em:
            return None
        filtro = [DispositivoEquipe.usuario_id == usuario_id]
        if id_ is not None:
            filtro.append(DispositivoEquipe.id == id_)
        removidos = db.scalars(delete(DispositivoEquipe).where(*filtro).returning(DispositivoEquipe.token_hash)).all()
        return id_ is None or bool(token and segredo('equipe-dispositivo', token) in removidos)
