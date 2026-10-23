"""Painel e detalhe reais via HTTP/ORM em memória; nenhum banco externo."""
import asyncio
from decimal import Decimal
from urllib.parse import urlencode
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from test_filiais import unidades, http_app, request


@pytest.fixture
def comandas(unidades):
    from app.models import Comanda, ItemComanda
    s = unidades
    s.commands = {}
    for key, booking in s.bookings.items():
        command = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == booking.id))
        s.commands[key] = command
    s.commands[('barbeiro', 'A')].status = 'aberta'
    s.commands[('itinerante', 'A')].status = 'aberta'
    s.commands[('barbeiro_chefe', 'A')].status = 'fechada'
    # Total armazenado propositalmente diferente: painel usa soma real dos itens.
    s.commands[('barbeiro', 'A')].valor_total = 99999
    s.db.add(ItemComanda(comanda_id=s.commands[('barbeiro', 'A')].id,
                        tipo='servico', descricao='Adicional histórico', quantidade=2,
                        preco_unitario=Decimal('12.50')))
    s.db.commit()
    return s


def consultar(app, s, role='admin', **params):
    from app.core.security import criar_token
    query = urlencode({'filial_id': s.a.id, **params})
    return asyncio.run(request(app, f'/comandas/painel?{query}', criar_token(s.users[role].id)))


def test_painel_pagina_no_banco_e_indicadores_sem_duplicar_itens(http_app, comandas):
    s = comandas
    code, result = consultar(http_app, s, tamanho=1)
    assert code == 200 and result['total'] == 3 and len(result['itens']) == 1
    assert result['indicadores'] == {
        'contagens': {'pendente': 0, 'aberta': 2, 'fechada': 1, 'cancelada': 0},
        'valor_abertas': '85.00', 'pagamentos_disponiveis': False,
    }
    ids = []
    for page in (1, 2, 3):
        _, data = consultar(http_app, s, tamanho=1, pagina=page)
        ids.extend(row['id'] for row in data['itens'])
        assert data['indicadores'] == result['indicadores']
    assert len(set(ids)) == 3
    assert consultar(http_app, s, tamanho=1, pagina=4)[1]['itens'] == []


def test_aba_status_nao_limita_indicadores_e_filtros_tem_semantica_explicita(http_app, comandas):
    s = comandas
    code, result = consultar(http_app, s, status='fechada', data_inicio='2099-01-01', data_fim='2099-01-01')
    assert code == 200 and result['total'] == 1
    assert result['indicadores']['contagens']['aberta'] == 2
    assert result['indicadores']['valor_abertas'] == '85.00'
    _, empty = consultar(http_app, s, data_inicio='2099-01-02')
    assert empty['total'] == 0 and empty['indicadores']['valor_abertas'] == '0.00'
    assert set(empty['indicadores']['contagens'].values()) == {0}
    _, filtered = consultar(http_app, s, profissional_id=s.users['barbeiro'].id)
    assert filtered['total'] == 1 and filtered['indicadores']['valor_abertas'] == '55.00'


@pytest.mark.parametrize('busca', ['Cliente GLOBAL', '  cliente global  '])
def test_pesquisa_cliente(http_app, comandas, busca):
    assert consultar(http_app, comandas, busca=busca)[1]['total'] == 3


def test_busca_uuid_completo_e_prefixo_e_caracteres_literais(http_app, comandas):
    s = comandas
    ident = str(s.commands[('barbeiro', 'A')].id)
    for termo in (ident, ident[:8], ident.upper(), ident.replace('-', '')):
        code, result = consultar(http_app, s, busca=termo)
        assert code == 200 and result['total'] == 1
        assert result['itens'][0]['id'] == ident
    for termo in ('%', '_', "' OR 1=1 --"):
        assert consultar(http_app, s, busca=termo)[1]['total'] == 0


@pytest.mark.parametrize('role,total,abertas', [('admin', 3, 2), ('recepcao', 3, 2), ('barbeiro_chefe', 3, 2), ('barbeiro', 1, 1)])
def test_painel_respeita_profissional_filial_e_indicadores(http_app, comandas, role, total, abertas):
    s = comandas
    code, result = consultar(http_app, s, role)
    assert code == 200 and result['total'] == total
    assert result['indicadores']['contagens']['aberta'] == abertas
    assert all(row['filial_id'] == str(s.a.id) for row in result['itens'])
    if role == 'barbeiro':
        assert {row['barbeiro_id'] for row in result['itens']} == {str(s.users[role].id)}
        assert consultar(http_app, s, role, profissional_id=s.users['itinerante'].id)[0] == 403
    assert consultar(http_app, s, role, filial_id=s.b.id)[0] == (200 if role == 'admin' else 403)


def test_detalhe_enriquecido_total_historico_e_sem_escritas(http_app, comandas):
    from app.core.security import criar_token
    s = comandas
    ident = s.commands[('barbeiro', 'A')].id
    statements = []
    def capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    engine = s.db.get_bind()
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        code, detail = asyncio.run(request(http_app, f'/comandas/{ident}?filial_id={s.a.id}', criar_token(s.users['recepcao'].id)))
        assert code == 200
        assert detail['cliente'] == {'id': str(s.client.id), 'nome': s.client.nome}
        assert detail['profissional']['nome'] == 'barbeiro'
        assert detail['atendimento']['data'] == '2099-01-01'
        assert detail['atendimento']['hora_inicio'] == '09:00:00'
        assert detail['filial']['nome'] == 'A'
        assert detail['total'] == '55.00'
        assert sorted(item['subtotal'] for item in detail['itens']) == ['25.00', '30.00']
        assert 'senha' not in str(detail) and 'telefone' not in str(detail)
        assert consultar(http_app, s)[0] == 200
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert not {'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP'} & set(statements)


def test_detalhe_oculta_terceiros_contexto_incorreto_e_inexistentes(http_app, comandas):
    from app.core.security import criar_token
    s = comandas
    ident = s.commands[('itinerante', 'A')].id
    token = criar_token(s.users['barbeiro'].id)
    for path in (f'/comandas/{ident}', f'/comandas/{uuid4()}'):
        assert asyncio.run(request(http_app, path, token))[0] == 404
    admin = criar_token(s.users['admin'].id)
    assert asyncio.run(request(http_app, f'/comandas/{ident}?filial_id={s.b.id}', admin))[0] == 404


def test_revogacao_nao_vaza_painel_ou_detalhe(http_app, comandas):
    from app.models import UsuarioFilial
    from app.core.security import criar_token
    s = comandas
    user = s.users['recepcao']
    token = criar_token(user.id)
    ident = s.commands[('barbeiro', 'A')].id
    link = s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == user.id))
    link.ativo = False
    s.db.commit()
    assert consultar(http_app, s, 'recepcao')[0] == 403
    assert asyncio.run(request(http_app, f'/comandas/{ident}', token))[0] == 404


@pytest.mark.parametrize('params', [
    {'pagina': 0}, {'tamanho': 0}, {'tamanho': 49}, {'status': 'paga'},
    {'busca': 'x' * 101}, {'data_inicio': 'inválida'},
    {'data_inicio': '2099-02-01', 'data_fim': '2099-01-01'},
    {'profissional_id': 'invalido'},
])
def test_parametros_invalidos_422(http_app, comandas, params):
    assert consultar(http_app, comandas, **params)[0] == 422


def test_sem_sessao_negado_e_listagem_legada_preservada(http_app, comandas):
    from app.core.security import criar_token
    s = comandas
    assert asyncio.run(request(http_app, '/comandas/painel', 'invalido'))[0] == 401
    code, result = asyncio.run(request(http_app, f'/comandas?filial_id={s.a.id}', criar_token(s.users['admin'].id)))
    assert code == 200 and isinstance(result, list) and len(result) == 3
