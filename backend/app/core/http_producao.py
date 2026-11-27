"""Fronteira ASGI para TLS, proxy e cabeçalhos do ambiente publicado."""
import os
from ipaddress import IPv6Address, ip_address, ip_network
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.core.ambiente import origem_http


def endereco(valor):
    if '%' in valor:
        raise ValueError
    ip = ip_address(valor)
    if isinstance(ip, IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


def redes_confiaveis():
    valor = os.getenv('BACKEND_TRUSTED_PROXY_CIDRS', '').strip()
    try:
        redes = tuple(ip_network(item.strip()) for item in valor.split(',')) if valor else ()
        if any(rede.prefixlen == 0 for rede in redes):
            raise ValueError
        return redes
    except ValueError:
        raise RuntimeError('BACKEND_TRUSTED_PROXY_CIDRS exige IPs ou CIDRs explícitos') from None


def politica_conteudo():
    imagens = "'self' data: blob:"
    if storage := os.getenv('SUPABASE_URL'):
        try:
            imagens += ' ' + origem_http(storage.rstrip('/'), somente_https=True)
        except ValueError:
            raise RuntimeError('SUPABASE_URL deve ser uma origem HTTPS válida') from None
    return '; '.join((
        "default-src 'none'", "base-uri 'none'", "object-src 'none'",
        "frame-ancestors 'none'", "form-action 'self'", "script-src 'self'",
        "style-src 'self' https://fonts.googleapis.com", "style-src-attr 'unsafe-inline'",
        "font-src 'self' https://fonts.gstatic.com", f"img-src {imagens}",
        "connect-src 'self'", "frame-src https://maps.google.com https://www.google.com",
        "manifest-src 'self'", "upgrade-insecure-requests",
    ))


class HTTPProducao:
    def __init__(self, app, origens):
        self.app = app
        self.redes = redes_confiaveis()
        self.hosts = {urlsplit(origem).netloc for origem in origens}
        self.csp = politica_conteudo()

    def confiavel(self, ip):
        return any(ip in rede for rede in self.redes)

    def encaminhar(self, scope, headers, peer):
        protocolos = headers.getlist('x-forwarded-proto')
        if protocolos and protocolos not in (['https'], ['http']):
            raise ValueError
        cadeias = headers.getlist('x-forwarded-for')
        if not cadeias:
            if protocolos:
                raise ValueError
            return scope
        if len(cadeias) != 1 or len(cadeias[0]) > 2048:
            raise ValueError
        saltos = [endereco(item.strip()) for item in cadeias[0].split(',')]
        ip = next((ip for ip in reversed(saltos) if not self.confiavel(ip)), peer)
        return dict(scope, client=(str(ip), 0), scheme=protocolos[0] if protocolos else scope['scheme'])

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        original = scope
        peer = None
        confiavel = False
        resposta = None
        try:
            if scope.get('client'):
                peer = endereco(scope['client'][0])
                # Normalize IPv4-mapped peers even on a direct TLS connection.
                scope = dict(scope, client=(str(peer), scope['client'][1]))
                confiavel = self.confiavel(peer)
                if confiavel:
                    scope = self.encaminhar(scope, headers, peer)
        except ValueError:
            resposta = JSONResponse({'detail': 'Encaminhamento inválido'}, status_code=400)

        tls = scope['scheme'] == 'https'
        sonda = (not tls and original['scheme'] == 'http' and peer is not None
                 and (confiavel or peer.is_loopback)
                 and not headers.getlist('x-forwarded-proto')
                 and scope['path'] in {'/health', '/ready'} and scope['method'] in {'GET', 'HEAD'})
        hosts = headers.getlist('host')
        if resposta is None and not sonda:
            if len(hosts) != 1 or hosts[0].lower() not in self.hosts:
                resposta = JSONResponse({'detail': 'Host inválido'}, status_code=400)
            elif not tls:
                resposta = JSONResponse({'detail': 'HTTPS obrigatório'}, status_code=400)

        async def proteger(message):
            if message['type'] == 'http.response.start':
                saida = MutableHeaders(scope=message)
                saida['Content-Security-Policy'] = self.csp
                saida['X-Content-Type-Options'] = 'nosniff'
                saida['Referrer-Policy'] = 'strict-origin-when-cross-origin'
                saida['X-Frame-Options'] = 'DENY'
                if tls:
                    saida['Strict-Transport-Security'] = 'max-age=31536000'
                if message['status'] >= 400 or 'set-cookie' in saida:
                    saida['Cache-Control'] = 'no-store'
            await send(message)

        await (resposta if resposta is not None else self.app)(scope, receive, proteger)
