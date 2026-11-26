import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from sqlalchemy.orm import Session


def test_catalogo_permite_criar_e_vincular_varias_categorias(runtime_pg):
    from app.api.deps import get_current_user, get_db
    from app.api.routes.servico import router
    from app.models.usuario import PerfilEnum

    app = FastAPI()
    app.include_router(router)
    operador = SimpleNamespace(id=uuid4(), perfil=PerfilEnum.BARBEIRO)

    def sessao():
        with Session(runtime_pg) as db:
            yield db

    app.dependency_overrides[get_db] = sessao
    app.dependency_overrides[get_current_user] = lambda: operador

    def enviar(metodo, caminho, dados=None):
        async def executar():
            mensagens = []

            async def receber():
                return {'type': 'http.request', 'body': json.dumps(dados).encode(), 'more_body': False}

            async def enviar_mensagem(mensagem):
                mensagens.append(mensagem)

            await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                       'scheme': 'http', 'method': metodo, 'path': caminho, 'root_path': '',
                       'query_string': b'', 'headers': [(b'content-type', b'application/json')]},
                      receber, enviar_mensagem)
            return mensagens[0]['status'], json.loads(mensagens[1]['body'])

        return asyncio.run(executar())

    assert enviar('POST', '/servicos/categorias', {'nome': 'Corte'})[0] == 403
    operador.perfil = PerfilEnum.ADMIN
    assert enviar('POST', '/servicos/categorias', {'nome': '   '})[0] == 422
    _, corte = enviar('POST', '/servicos/categorias', {'nome': ' Corte '})
    _, barba = enviar('POST', '/servicos/categorias', {'nome': 'Barba'})
    assert corte['nome'] == 'Corte'
    assert enviar('POST', '/servicos/categorias', {'nome': 'corte'}) == (200, corte)
    assert enviar('GET', '/servicos/categorias') == (200, [barba, corte])

    dados = {'nome': 'Atendimento combinado', 'preco': 50, 'tempo_estimado': 30, 'comissao_padrao': 20}
    status, servico = enviar('POST', '/servicos/', dados | {'categorias_ids': [corte['id'], barba['id']]})
    assert status == 201, servico
    esperado = {corte['id'], barba['id']}
    assert {item['id'] for item in servico['categorias']} == esperado

    url = f'/servicos/{servico["id"]}'
    assert enviar('PUT', url, {'categorias_ids': [str(uuid4())]})[0] == 422
    _, publico = enviar('GET', url)
    assert {item['id'] for item in publico['categorias']} == esperado
    assert 'comissao_padrao' not in publico
    _, atualizado = enviar('PUT', url, {'preco': 60})
    assert {item['id'] for item in atualizado['categorias']} == esperado
    assert enviar('PUT', url, {'categorias_ids': []})[1]['categorias'] == []
    assert enviar('POST', '/servicos/', dados)[1]['categorias'] == []
