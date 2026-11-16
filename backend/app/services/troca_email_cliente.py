"""Troca de identidade exige posse dos dois contatos; nunca exige senha antiga."""
import hmac
import secrets
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, update, delete, or_, func, text
from app.models import Cliente, ContaPortalCliente, DesafioPortalCliente, SessaoPortalCliente
from app.models.portal_cliente import TrocaEmailCliente as Troca
from app.services import portal_cliente as portal, entrega_codigo_cliente as entrega
from app.services.persistencia import transacao_escrita


def ocupado(db, email, ignorar=None):
    clientes = select(Cliente.id).where(func.lower(func.trim(Cliente.email)) == email)
    contas = select(ContaPortalCliente.cliente_id).where(func.lower(ContaPortalCliente.email_confirmado) == email)
    if ignorar:
        clientes = clientes.where(Cliente.id != ignorar)
        contas = contas.where(ContaPortalCliente.cliente_id != ignorar)
    return db.scalar(clientes.limit(1)) is not None or db.scalar(contas.limit(1)) is not None


def solicitar(db, dados, ip):
    entrega.configuracao()
    id_, codigo = uuid4(), f'{secrets.randbelow(1000000):06d}'
    with transacao_escrita(db):
        permitido = (portal._bucket(db, 'troca:ip:' + ip, 10, 3600)
                     and portal._bucket(db, 'troca:email:' + dados.email, 5, 3600, 60)
                     and portal._bucket(db, 'troca:destino:' + dados.email_novo, 5, 3600, 60))
        clientes = portal._candidatos(db, dados.email)
        cliente = clientes[0] if len(clientes) == 1 else None
        conta = db.get(ContaPortalCliente, cliente.id) if cliente else None
        if (permitido and cliente and conta and cliente.conta_ativada
                and portal._contato_compativel(cliente, dados.email)
                and conta.email_confirmado == dados.email and dados.email != dados.email_novo):
            db.add(Troca(id=id_, cliente_id=cliente.id, email_atual=dados.email,
                         email_novo=dados.email_novo, versao=conta.versao,
                         codigo_hash=portal.segredo('troca:atual', str(id_) + ':' + codigo),
                         expira_em=portal.agora() + timedelta(minutes=10)))
    # Same generic mail/response for syntactically valid but ineligible requests.
    if permitido:
        try:
            entrega.enviar(dados.email, codigo)
        except entrega.EntregaIndisponivel:
            with transacao_escrita(db):
                item = db.get(Troca, id_)
                if item:
                    item.consumido = True
            raise
    return {'solicitacao_id': id_, 'mensagem': 'Se o pedido for válido, confirme o código enviado ao e-mail atual. Aguarde 60 segundos antes de solicitar outro.'}


def confirmar(db, dados, ip, etapa):
    valido, proximo = False, None
    with transacao_escrita(db), db.no_autoflush:
        permitido = portal._bucket(db, 'troca:confirmacao:ip:' + ip, 30, 3600)
        # The same lock order as signup avoids racing reception and other identity changes.
        if db.get_bind().dialect.name == 'postgresql':
            db.execute(text('SELECT public.portal_bloquear_clientes()'))
        item = db.scalar(select(Troca).where(Troca.id == dados.solicitacao_id).with_for_update()
                         .execution_options(populate_existing=True)) if permitido else None
        if item and not item.consumido and item.etapa == etapa:
            if portal.utc(item.expira_em) <= portal.agora() or item.tentativas >= 5:
                item.consumido = True
            else:
                item.tentativas += 1
                correto = hmac.compare_digest(item.codigo_hash, portal.segredo('troca:' + etapa, str(item.id) + ':' + dados.codigo))
                cliente = db.scalar(select(Cliente).where(Cliente.id == item.cliente_id).with_for_update().execution_options(populate_existing=True))
                conta = db.scalar(select(ContaPortalCliente).where(ContaPortalCliente.cliente_id == item.cliente_id).with_for_update().execution_options(populate_existing=True))
                elegivel = (cliente and conta and cliente.conta_ativada and portal._contato_compativel(cliente, item.email_atual)
                            and conta.email_confirmado == item.email_atual and conta.versao == item.versao)
                if correto and elegivel:
                    if ocupado(db, item.email_novo, cliente.id):
                        item.consumido = True
                    elif etapa == 'atual':
                        codigo = f'{secrets.randbelow(1000000):06d}'
                        item.etapa, item.tentativas = 'novo', 0
                        item.codigo_hash = portal.segredo('troca:novo', str(item.id) + ':' + codigo)
                        item.expira_em = portal.agora() + timedelta(minutes=10)
                        proximo = (item.email_novo, codigo)
                        valido = True
                    else:
                        conta.email_confirmado = cliente.email = item.email_novo
                        conta.verificado_em = portal.agora()
                        conta.versao += 1
                        db.execute(delete(SessaoPortalCliente).where(SessaoPortalCliente.cliente_id == cliente.id))
                        db.execute(update(DesafioPortalCliente).where(or_(DesafioPortalCliente.cliente_id == cliente.id,
                            DesafioPortalCliente.email.in_([item.email_atual, item.email_novo]))).values(consumido=True, dados=None))
                        db.execute(update(Troca).where(Troca.cliente_id == cliente.id).values(consumido=True))
                        item.consumido = True
                        valido = True
                if item.tentativas >= 5:
                    item.consumido = True
        db.flush()
    if not valido:
        raise portal.PortalFalha(400, 'Código inválido, expirado ou troca indisponível. Confira os dados ou procure a recepção.')
    if proximo:
        try:
            entrega.enviar(*proximo)
        except entrega.EntregaIndisponivel:
            with transacao_escrita(db):
                db.get(Troca, dados.solicitacao_id).consumido = True
            raise
    return {'mensagem': 'Confirme agora o código enviado ao novo e-mail.' if proximo else 'E-mail atualizado. As sessões anteriores foram encerradas. Entre ou recupere sua senha com o novo e-mail.'}
