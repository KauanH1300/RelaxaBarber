"""Contratos reais de clientes, exclusivamente com ORM/HTTP em memória."""
import asyncio
from uuid import UUID

import pytest
from pydantic import ValidationError

from test_filiais import unidades, http_app, request


def email_com_tamanho(tamanho):
    # Endereço sintaticamente válido; cada label do domínio tem até 63 caracteres.
    return 'a' * 64 + '@' + 'b' * 63 + '.' + 'c' * 63 + '.' + 'd' * (tamanho - 197) + '.com'


@pytest.mark.parametrize('schema_name', ['ClienteCreate', 'ClienteUpdate'])
def test_schemas_normalizam_bordas_e_respeitam_limites(isolated_runtime, models, schema_name):
    from app.schemas import cliente
    schema = getattr(cliente, schema_name)
    dados = schema(nome=' \tAna  Silva\n', telefone='  +55 (81) 99999-9999  ', email=' ana@example.com ')
    assert dados.nome == 'Ana  Silva'
    assert dados.telefone == '+55 (81) 99999-9999'
    assert dados.email == 'ana@example.com'
    # EmailStr já limita endereços ASCII a 254, abaixo da coluna de 255.
    limites = schema(nome=' ' + 'á' * 150 + ' ', telefone=' ' + '1' * 20 + ' ', email=email_com_tamanho(254))
    assert len(limites.nome) == models.Cliente.__table__.c.nome.type.length
    assert len(limites.telefone) == models.Cliente.__table__.c.telefone.type.length
    assert len(limites.email) == 254
    assert len(limites.email) <= models.Cliente.__table__.c.email.type.length


def test_patch_distingue_omissao_de_null(isolated_runtime):
    from app.schemas.cliente import ClienteUpdate
    omitido = ClienteUpdate()
    assert omitido.model_fields_set == set()
    assert omitido.model_dump(exclude_unset=True) == {}
    assert ClienteUpdate(email=None).model_dump(exclude_unset=True) == {'email': None}
    assert ClienteUpdate(nome=' Ana ').model_dump(exclude_unset=True) == {'nome': 'Ana'}
    for campo in ('nome', 'telefone'):
        with pytest.raises(ValidationError):
            ClienteUpdate(**{campo: None})


@pytest.mark.parametrize('metodo', ['POST', 'PATCH'])
@pytest.mark.parametrize('campo,valor', [
    ('nome', ''), ('nome', ' \t\n'), ('nome', None), ('nome', 'a' * 151),
    ('telefone', ''), ('telefone', ' \t\n'), ('telefone', None), ('telefone', '1' * 21),
    ('email', 'invalido'), ('email', email_com_tamanho(255)), ('email', email_com_tamanho(256)),
])
def test_http_entrada_invalida_retorna_422_sem_alteracoes(http_app, unidades, metodo, campo, valor):
    from app.core.security import criar_token
    from app.models import Cliente, ClienteFilial
    s = unidades
    before = (s.db.query(Cliente).count(), s.db.query(ClienteFilial).count(),
              s.client.nome, s.client.telefone, s.client.email)
    payload = {'nome': 'Novo', 'telefone': 'novo-valido', 'filial_id': str(s.a.id)} if metodo == 'POST' else {}
    payload[campo] = valor
    url = '/clientes' if metodo == 'POST' else f'/clientes/{s.client.id}?filial_id={s.a.id}'
    code, body = asyncio.run(request(http_app, url, criar_token(s.users['recepcao'].id), metodo, payload))
    assert code == 422
    assert any(erro['loc'][-1] == campo for erro in body['detail'])
    s.db.expire_all()
    assert before == (s.db.query(Cliente).count(), s.db.query(ClienteFilial).count(),
                      s.client.nome, s.client.telefone, s.client.email)


def test_http_cria_edita_e_remove_email_preservando_omitidos(http_app, unidades):
    from app.core.security import criar_token
    from app.models import ClienteFilial
    s = unidades
    token = criar_token(s.users['recepcao'].id)
    code, criado = asyncio.run(request(http_app, '/clientes', token, 'POST', {
        'filial_id': str(s.a.id), 'nome': ' \tAna  Silva ',
        'telefone': ' +55 (81) 99999-9999 ', 'email': ' ana@example.com ',
    }))
    assert code == 201
    assert (criado['nome'], criado['telefone'], criado['email']) == ('Ana  Silva', '+55 (81) 99999-9999', 'ana@example.com')
    url = f"/clientes/{criado['id']}?filial_id={s.a.id}"
    code, editado = asyncio.run(request(http_app, url, token, 'PATCH', {'nome': ' Ana Souza '}))
    assert code == 200
    assert (editado['nome'], editado['telefone'], editado['email']) == ('Ana Souza', criado['telefone'], criado['email'])
    code, editado = asyncio.run(request(http_app, url, token, 'PATCH', {'telefone': '  (81) 98888-7777  ', 'email': None}))
    assert code == 200
    assert (editado['nome'], editado['telefone'], editado['email']) == ('Ana Souza', '(81) 98888-7777', None)
    assert s.db.query(ClienteFilial).filter_by(cliente_id=UUID(criado['id'])).count() == 1


def test_http_patch_vazio_preserva_cadastro(http_app, unidades):
    from app.core.security import criar_token
    s = unidades

    class CorpoVazio(dict):
        def __bool__(self):
            return True

    # Garante que o helper ASGI envie {} em vez de nenhum corpo.
    payload = CorpoVazio()
    before = (s.client.nome, s.client.telefone, s.client.email)
    code, resultado = asyncio.run(request(http_app, f'/clientes/{s.client.id}?filial_id={s.a.id}',
                                        criar_token(s.users['recepcao'].id), 'PATCH', payload))
    assert code == 200
    assert (resultado['nome'], resultado['telefone'], resultado['email']) == before


@pytest.mark.parametrize('metodo', ['POST', 'PATCH'])
def test_http_aceita_limites_maximos(http_app, unidades, metodo):
    from app.core.security import criar_token
    s = unidades
    payload = {'nome': 'á' * 150, 'telefone': '1' * 20, 'email': email_com_tamanho(254)}
    if metodo == 'POST':
        payload['filial_id'] = str(s.a.id)
    url = '/clientes' if metodo == 'POST' else f'/clientes/{s.client.id}?filial_id={s.a.id}'
    code, resultado = asyncio.run(request(http_app, url, criar_token(s.users['recepcao'].id), metodo, payload))
    assert code == (201 if metodo == 'POST' else 200)
    assert resultado['nome'] == payload['nome']
    assert resultado['telefone'] == payload['telefone']
    assert resultado['email'] == payload['email']


def test_unicidade_considera_telefone_apos_trim(http_app, unidades):
    from app.core.security import criar_token
    s = unidades
    code, _ = asyncio.run(request(http_app, '/clientes', criar_token(s.users['recepcao'].id), 'POST', {
        'filial_id': str(s.a.id), 'nome': 'Outro', 'telefone': f' {s.client.telefone} ',
    }))
    assert code == 409
