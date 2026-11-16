"""Entrega SMTP real com TLS obrigatório; sem fallback para log/console."""
import os
import smtplib
import ssl
from email.message import EmailMessage


class EntregaIndisponivel(Exception):
    pass


def configuracao():
    host = os.getenv('CLIENT_PORTAL_SMTP_HOST', '')
    remetente = os.getenv('CLIENT_PORTAL_SMTP_FROM', '')
    modo = os.getenv('CLIENT_PORTAL_SMTP_TLS', 'ssl')
    usuario = os.getenv('CLIENT_PORTAL_SMTP_USER', '')
    senha = os.getenv('CLIENT_PORTAL_SMTP_PASSWORD', '')
    try:
        porta = int(os.getenv('CLIENT_PORTAL_SMTP_PORT', '465' if modo == 'ssl' else '587'))
    except ValueError:
        raise EntregaIndisponivel() from None
    if not host or not remetente or '\n' in remetente or '\r' in remetente or modo not in ('ssl', 'starttls'):
        raise EntregaIndisponivel()
    if bool(usuario) != bool(senha) or not 1 <= porta <= 65535:
        raise EntregaIndisponivel()
    return host, porta, remetente, modo, usuario, senha


def enviar(email, codigo):
    host, porta, remetente, modo, usuario, senha = configuracao()
    mensagem = EmailMessage()
    mensagem['From'] = remetente
    mensagem['To'] = email
    mensagem['Subject'] = 'Seu código de acesso ao RelaxaBarber'
    mensagem.set_content(f'Seu código de verificação é {codigo}. Ele expira em 10 minutos e pode ser usado uma vez.\n'
                         'Não compartilhe este código. Se você não solicitou acesso, ignore esta mensagem.\n'
                         'A confirmação depende da validade e da compatibilidade dos dados do pedido.')
    try:
        context = ssl.create_default_context(cafile=os.getenv('CLIENT_PORTAL_SMTP_CA_FILE') or None)
        factory = smtplib.SMTP_SSL if modo == 'ssl' else smtplib.SMTP
        kwargs = {'context': context} if modo == 'ssl' else {}
        with factory(host, porta, timeout=10, **kwargs) as smtp:
            if modo == 'starttls':
                smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
            if usuario:
                smtp.login(usuario, senha)
            recusados = smtp.send_message(mensagem)
            if recusados:
                raise EntregaIndisponivel()
    except Exception:
        # Não propagar respostas do servidor, destinatários ou credenciais.
        raise EntregaIndisponivel() from None
