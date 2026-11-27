"""Contas verificadas, com limites e sessões persistidos no banco."""
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
import hmac
import secrets
from uuid import uuid4
from sqlalchemy import select, text, delete, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models import Cliente, ContaPortalCliente as Conta, DesafioPortalCliente as Desafio, LimitePortalCliente as Limite, SessaoPortalCliente as Sessao
from app.core.security import SECRET_KEY, hash_senha, verificar_senha, autenticar_senha
from app.schemas.portal_cliente import PerfilPortal
from app.services.persistencia import transacao_escrita
from app.services import entrega_codigo_cliente as entrega


class PortalFalha(Exception):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail


def agora():
    return datetime.now(timezone.utc)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def segredo(tipo, value):
    return hmac.new(SECRET_KEY.encode(), ('portal-clientes-v1:' + tipo + ':' + value).encode(), sha256).hexdigest()


def _bucket(db, chave, maximo, segundos, intervalo=0):
    agora_ = agora()
    chave = segredo('limite', chave)
    insert = pg_insert if db.get_bind().dialect.name == 'postgresql' else sqlite_insert
    db.execute(insert(Limite).values(chave=chave, inicio=agora_, ultimo=agora_ - timedelta(days=1), quantidade=0)
               .on_conflict_do_nothing(index_elements=['chave']))
    item = db.scalar(select(Limite).where(Limite.chave == chave).with_for_update().execution_options(populate_existing=True))
    if utc(item.inicio) + timedelta(seconds=segundos) <= agora_:
        item.inicio, item.quantidade = agora_, 0
    if item.quantidade >= maximo or utc(item.ultimo) + timedelta(seconds=intervalo) > agora_:
        return False
    item.quantidade += 1
    item.ultimo = agora_
    return True


def conta_por_email(db, email):
    return db.scalar(select(Conta).where(Conta.email_confirmado == email)
                     .execution_options(populate_existing=True))


def admitir_busca_para_associacao(db, operador_id):
    return _bucket(db, f'associacao:operador:{operador_id}', 30, 3600)


def _contato_compativel(cliente, email):
    return cliente.ativo and cliente.email and cliente.email.strip().lower() == email


def solicitar(db, dados, ip, finalidade):
    # Ausência de SMTP nunca é disfarçada como verificação funcional.
    entrega.configuracao()
    id_, codigo = uuid4(), f'{secrets.randbelow(1000000):06d}'
    admitido = False
    with transacao_escrita(db):
        if _bucket(db, 'codigo:ip:' + ip, 10, 3600) and _bucket(db, 'codigo:email:' + dados.email, 5, 3600, 60):
            admitido = True
            conta = conta_por_email(db, dados.email)
            payload, cliente_id = None, None
            if finalidade == 'cadastro':
                senha_hash = hash_senha(dados.senha)
                if conta is None:
                    payload = dict(nome=dados.nome, telefone=dados.telefone, senha_hash=senha_hash)
            elif conta:
                cliente = db.get(Cliente, conta.cliente_id)
                if cliente and _contato_compativel(cliente, dados.email) and cliente.conta_ativada:
                    payload, cliente_id = {'versao': conta.versao}, cliente.id
            db.execute(update(Desafio).where(
                Desafio.email == dados.email, Desafio.finalidade == finalidade,
                Desafio.consumido.is_(False),
            ).values(consumido=True, dados=None))
            db.add(Desafio(id=id_, finalidade=finalidade, codigo_hash=segredo('codigo', str(id_) + ':' + codigo),
                email=dados.email, cliente_id=cliente_id, dados=payload, expira_em=agora() + timedelta(minutes=10)))
    if admitido:
        try:
            # Mesmo e-mail genérico para pedidos elegíveis e inelegíveis: sem enumeração por tempo de SMTP.
            entrega.enviar(dados.email, codigo)
        except entrega.EntregaIndisponivel:
            with transacao_escrita(db):
                desafio = db.get(Desafio, id_)
                desafio.consumido, desafio.dados = True, None
            raise
    return {'solicitacao_id': id_, 'mensagem': 'Se o pedido for válido, use o código enviado ao e-mail informado. Confira também o spam.'}


def confirmar(db, dados, ip, finalidade):
    valido = False
    codigo_hash = segredo('codigo', str(dados.solicitacao_id) + ':' + dados.codigo)
    with transacao_escrita(db), db.no_autoflush:
        permitido = _bucket(db, 'confirmacao:ip:' + ip, 30, 3600)
        # A troca de e-mail também bloqueia clientes antes de invalidar desafios.
        previa = db.get(Desafio, dados.solicitacao_id) if permitido else None
        if (previa and previa.finalidade == finalidade and not previa.consumido and previa.dados
                and utc(previa.expira_em) > agora() and previa.tentativas < 5
                and hmac.compare_digest(previa.codigo_hash, codigo_hash)
                and db.get_bind().dialect.name == 'postgresql'):
            db.execute(text('SELECT public.portal_bloquear_clientes()'))
        desafio = db.scalar(select(Desafio).where(Desafio.id == dados.solicitacao_id)
                            .with_for_update().execution_options(populate_existing=True)) if previa else None
        if desafio and not desafio.consumido and desafio.finalidade == finalidade:
            if utc(desafio.expira_em) <= agora() or desafio.tentativas >= 5:
                desafio.consumido, desafio.dados = True, None
            else:
                desafio.tentativas += 1
                correto = hmac.compare_digest(desafio.codigo_hash, codigo_hash)
                if correto:
                    payload = desafio.dados
                    desafio.consumido, desafio.dados = True, None
                    if payload:
                        conta = conta_por_email(db, desafio.email)
                        if finalidade == 'cadastro':
                            if conta is None:
                                cliente = Cliente(nome=payload['nome'], telefone=payload['telefone'],
                                                  email=desafio.email, senha_hash=payload['senha_hash'],
                                                  conta_ativada=True)
                                db.add(cliente); db.flush()
                                db.add(Conta(cliente_id=cliente.id, email_confirmado=desafio.email))
                                valido = True
                        elif conta and conta.cliente_id == desafio.cliente_id and conta.versao == payload['versao']:
                            cliente = db.get(Cliente, conta.cliente_id)
                            if cliente and _contato_compativel(cliente, desafio.email) and cliente.conta_ativada:
                                cliente.senha_hash = hash_senha(dados.senha)
                                conta.versao += 1
                                valido = True
                if desafio.tentativas >= 5:
                    desafio.consumido, desafio.dados = True, None
        db.flush()
    if not valido:
        raise PortalFalha(400, 'Código inválido, expirado ou pedido indisponível. Solicite outro código ou procure a recepção.')
    return {'mensagem': 'Conta ativada. Entre com seu e-mail e senha.' if finalidade == 'cadastro' else 'Senha redefinida. Entre novamente.'}


@lru_cache(maxsize=1)
def _hash_ficticio():
    return hash_senha('comparacao-interna-sem-conta-real')


def login(db, dados, ip):
    token, erro = None, None
    with transacao_escrita(db):
        permitido = _bucket(db, 'login:ip:' + ip, 30, 900) and _bucket(db, 'login:email:' + dados.email, 10, 900)
        if not permitido:
            erro = PortalFalha(429, 'Muitas tentativas. Aguarde antes de tentar novamente.')
        else:
            conta_inicial = conta_por_email(db, dados.email)
            cliente = db.scalar(select(Cliente).where(Cliente.id == conta_inicial.cliente_id)
                                .with_for_update().execution_options(populate_existing=True)) if conta_inicial else None
            conta = conta_por_email(db, dados.email) if cliente else None
            elegivel = (cliente and conta and _contato_compativel(cliente, dados.email) and cliente.conta_ativada
                        and conta.cliente_id == cliente.id and cliente.senha_hash)
            try:
                senha_correta, atualizado = autenticar_senha(dados.senha, cliente.senha_hash if elegivel else _hash_ficticio())
            except HTTPException:
                raise
            except Exception:
                senha_correta = False
            if not elegivel or not senha_correta:
                erro = PortalFalha(401, 'E-mail ou senha inválidos.')
            else:
                if atualizado:
                    cliente.senha_hash = atualizado
                token = secrets.token_urlsafe(32)
                db.add(Sessao(token_hash=segredo('sessao', token), cliente_id=cliente.id,
                    versao=conta.versao, expira_em=agora() + timedelta(hours=8)))
    if erro:
        raise erro
    return token


def autenticar(db, token):
    if not token or len(token) > 128:
        raise PortalFalha(401, 'Entre na sua conta de cliente.')
    sessao = db.scalar(select(Sessao).where(Sessao.token_hash == segredo('sessao', token)).execution_options(populate_existing=True))
    cliente = db.scalar(select(Cliente).where(Cliente.id == sessao.cliente_id).execution_options(populate_existing=True)) if sessao else None
    conta = db.scalar(select(Conta).where(Conta.cliente_id == sessao.cliente_id).execution_options(populate_existing=True)) if sessao else None
    if (not sessao or utc(sessao.expira_em) <= agora() or not cliente or not conta or
        not cliente.ativo or not cliente.conta_ativada or not cliente.senha_hash or
        sessao.versao != conta.versao or not _contato_compativel(cliente, conta.email_confirmado)):
        raise PortalFalha(401, 'Entre na sua conta de cliente.')
    return PerfilPortal.model_validate(cliente)


def logout(db, token):
    with transacao_escrita(db):
        if token and len(token) <= 128:
            db.execute(delete(Sessao).where(Sessao.token_hash == segredo('sessao', token)))
