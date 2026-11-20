"""Entrega o build React apenas para navegação HTML em rotas da SPA."""
import re
from pathlib import Path

from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

# Rotas compartilhadas, como /clientes, continuam sendo API para clientes JSON.
ROTAS = re.compile(
    r'/(?:login|cadastro|recuperar-senha|nova-senha|agendar|vitrine|clientes|funcionarios|'
    r'comandas|repasses|gerencial|estoque(?:/[^/]+/editar)?|expediente|perfil|agendamentos|'
    r'servicos(?:/novo|/[^/]+/editar)?|cliente(?:/(?:entrar|cadastro|recuperar|ativar|'
    r'redefinir|conta|trocar-email|agendamentos))?)?/?'
)


def aceita_html(accept):
    for tipo in accept.split(','):
        media, *params = tipo.strip().lower().split(';')
        if media.strip() == 'text/html':
            peso = next((p.strip()[2:] for p in params if p.strip().startswith('q=')), '1')
            try:
                if float(peso) > 0:
                    return True
            except ValueError:
                continue
    return False


class Frontend:
    def __init__(self, app, diretorio):
        self.app = app
        self.diretorio = Path(diretorio)
        if not (self.diretorio / 'index.html').is_file():
            raise RuntimeError('Build do frontend ausente')
        self.assets = StaticFiles(directory=self.diretorio)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('GET', 'HEAD'):
            await self.app(scope, receive, send)
            return
        path = scope['path']
        if path.startswith('/assets/') or path in ('/favicon.svg', '/icons.svg'):
            try:
                await self.assets(scope, receive, send)
            except HTTPException as exc:
                await JSONResponse({'detail': exc.detail}, status_code=exc.status_code, headers=exc.headers)(scope, receive, send)
            return
        if not ROTAS.fullmatch(path):
            await self.app(scope, receive, send)
            return
        if aceita_html(Headers(scope=scope).get('accept', '')):
            resposta = FileResponse(self.diretorio / 'index.html', headers={
                'Vary': 'Accept', 'Cache-Control': 'no-cache',
            })
            await resposta(scope, receive, send)
            return

        async def variar(message):
            if message['type'] == 'http.response.start':
                MutableHeaders(scope=message).add_vary_header('Accept')
            await send(message)

        await self.app(scope, receive, variar)
