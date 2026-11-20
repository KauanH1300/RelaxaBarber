from uuid import uuid4

from test_financeiro_http import api
from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso
from test_seguranca_horarios import chamar


def test_conferencia_por_operacao_sem_duplicatas_ou_acesso_cruzado(api, caso):
    from app.core.security import criar_token

    chave = uuid4()
    admin = criar_token(caso['atores']['admin'])
    recepcao = criar_token(caso['atores']['recepcao'])

    async def com_chave(scope, receive, send):
        scope = dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(chave).encode())])
        await api(scope, receive, send)

    filial = caso['filial']
    casos = [
        ('/clientes', '/clientes', {'nome': 'Cadastro teste', 'telefone': '81912340000', 'filial_id': str(filial)}),
        ('/usuarios', '/usuarios', {'nome': 'Equipe teste', 'email': 'equipe@example.org', 'perfil': 'barbeiro',
                                   'senha': 'Ficticia-9!', 'filial_ids': [str(filial)]}),
        ('/servicos/', '/servicos', {'nome': 'Serviço teste', 'preco': '20.00', 'comissao_padrao': '0', 'tempo_estimado': 30}),
    ]
    for caminho, prefixo, dados in casos:
        consulta = f'{prefixo}/cadastros/{chave}?filial_id={filial}'
        assert chamar(api, consulta, token=admin)[0] == 404
        status, criado = chamar(com_chave, caminho, method='POST', token=admin, dados=dados)
        assert status == 201, criado
        assert chamar(api, consulta, token=admin)[1]['id'] == criado['id']
        assert chamar(com_chave, caminho, method='POST', token=admin, dados=dados)[1]['id'] == criado['id']
        assert chamar(api, consulta, token=recepcao)[0] == (404 if prefixo == '/clientes' else 403)
        assert 'senha' not in criado and 'senha_hash' not in criado
    assert chamar(api, f"/clientes/cadastros/{chave}?filial_id={caso['outra_filial']}", token=admin)[0] == 404
