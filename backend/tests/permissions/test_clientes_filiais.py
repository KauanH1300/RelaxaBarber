"""Pesquisa global mínima e operações locais, com JWT e ORM reais em memória."""
import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select, event
from sqlalchemy.exc import IntegrityError

from test_filiais import unidades, http_app, request


@pytest.fixture
def cadastros(unidades):
    from app.models import Cliente, ClienteFilial
    s = unidades
    records = {}
    for key in ('apenas_a', 'apenas_b', 'livre', 'inativo'):
        records[key] = Cliente(nome=f'Cliente {key}', telefone=key, email=f'{key}@example.com', saldo=Decimal('987.65'), ativo=key != 'inativo')
    s.db.add_all(records.values())
    s.db.flush()
    s.db.add_all([
        ClienteFilial(cliente=records['apenas_a'], filial=s.a),
        ClienteFilial(cliente=records['apenas_b'], filial=s.b),
        ClienteFilial(cliente=records['inativo'], filial=s.a),
    ])
    s.db.commit()
    return records


@pytest.mark.parametrize('role', ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_pesquisa_global_ativa_minima_sem_selecao_ou_prioridade(http_app, unidades, cadastros, role):
    from app.core.security import criar_token
    s = unidades
    token = criar_token(s.users[role].id)
    code, found = asyncio.run(request(http_app, '/clientes/pesquisa', token))
    assert code == 200
    assert {row['id'] for row in found} == {str(c.id) for key, c in cadastros.items() if key != 'inativo'} | {str(s.client.id)}
    assert all(set(row) == {'id', 'nome', 'telefone'} for row in found)
    code, selected = asyncio.run(request(http_app, f'/clientes/pesquisa?filial_id={s.a.id}', token))
    assert code == 200 and selected == found
    code, filtered = asyncio.run(request(http_app, '/clientes/pesquisa?busca=apenas_b', token))
    assert code == 200 and [r['id'] for r in filtered] == [str(cadastros['apenas_b'].id)]
    if role == 'admin':
        assert asyncio.run(request(http_app, f'/clientes/pesquisa?filial_id={s.b.id}', token))[1] == found
    else:
        assert asyncio.run(request(http_app, f'/clientes/pesquisa?filial_id={s.b.id}', token))[0] == 403


def test_listagem_local_nao_duplicada_e_detalhe_externo_oculto(http_app, unidades, cadastros):
    from app.core.security import criar_token
    s = unidades
    admin = criar_token(s.users['admin'].id)
    for filial, key in ((s.a, 'apenas_a'), (s.b, 'apenas_b')):
        code, rows = asyncio.run(request(http_app, f'/clientes?filial_id={filial.id}', admin))
        assert code == 200 and {r['id'] for r in rows} == {str(s.client.id), str(cadastros[key].id)}
        assert all('saldo' not in row for row in rows)
    token = criar_token(s.users['recepcao'].id)
    client = cadastros['apenas_b']
    assert asyncio.run(request(http_app, f'/clientes/{client.id}', token))[0] == 404
    assert asyncio.run(request(http_app, f'/clientes/{client.id}', token, 'PATCH', {'nome': 'Não permitir'}))[0] == 404
    assert client.nome == 'Cliente apenas_b'
    assert asyncio.run(request(http_app, f'/clientes?filial_id={s.b.id}', token))[0] == 403
    assert asyncio.run(request(http_app, '/clientes', admin))[0] == 422


def test_pesquisa_nao_concede_acesso_a_comandas_ou_atendimentos(http_app, unidades, cadastros):
    from app.core.security import criar_token
    from app.models import Comanda
    s = unidades
    token = criar_token(s.users['recepcao'].id)
    assert asyncio.run(request(http_app, '/clientes/pesquisa', token))[0] == 200
    appointment = s.bookings[('outro', 'B')]
    command = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == appointment.id))
    for path in (f'/comandas/{command.id}', f'/agendamentos/{appointment.id}'):
        assert asyncio.run(request(http_app, path, token))[0] == 404
    assert asyncio.run(request(http_app, f'/agendamentos/{appointment.id}/status', token, 'PATCH', {'status': 'cancelado'}))[0] == 404


def test_cadastro_global_e_vinculo_local_no_mesmo_commit(http_app, unidades):
    from app.core.security import criar_token
    from app.models import Cliente, ClienteFilial
    s = unidades
    token = criar_token(s.users['recepcao'].id)
    code, created = asyncio.run(request(http_app, '/clientes', token, 'POST', {'nome': 'Novo', 'telefone': 'novo'}))
    assert code == 201 and 'saldo' not in created
    client = s.db.scalar(select(Cliente).where(Cliente.telefone == 'novo'))
    links = s.db.scalars(select(ClienteFilial).where(ClienteFilial.cliente_id == client.id)).all()
    assert len(links) == 1 and links[0].filial_id == s.a.id
    assert asyncio.run(request(http_app, '/clientes', token, 'POST', {'nome': 'Duplicado', 'telefone': 'novo'}))[0] == 409
    assert s.db.query(Cliente).filter(Cliente.telefone == 'novo').count() == 1
    assert s.db.query(ClienteFilial).filter(ClienteFilial.cliente_id == client.id).count() == 1


@pytest.mark.parametrize('phase', ['vinculo', 'commit'])
def test_cadastro_cliente_rollback_integral(unidades, phase):
    from app.api.routes.clientes import criar_cliente
    from app.schemas.cliente import ClienteCreate
    from app.models import Cliente, ClienteFilial
    from app.services.persistencia import FalhaPersistencia
    s = unidades
    baseline = (s.db.query(Cliente).count(), s.db.query(ClienteFilial).count())
    def fail_sql(conn, cursor, statement, params, context, many):
        if statement.startswith('INSERT INTO cliente_filiais '):
            raise IntegrityError('teste', {}, Exception('falha induzida'))
    def fail_commit(session):
        session.flush()
        raise IntegrityError('teste', {}, Exception('falha induzida'))
    target, name, callback = (s.db.get_bind(), 'before_cursor_execute', fail_sql) if phase == 'vinculo' else (s.db, 'before_commit', fail_commit)
    event.listen(target, name, callback)
    try:
        with pytest.raises(FalhaPersistencia):
            criar_cliente(ClienteCreate(nome='Novo', telefone='rollback', filial_id=s.a.id), s.db, s.users['admin'])
    finally:
        event.remove(target, name, callback)
    assert (s.db.query(Cliente).count(), s.db.query(ClienteFilial).count()) == baseline


@pytest.mark.parametrize('phase', ['vinculo', 'comanda', 'commit'])
def test_primeiro_agendamento_reverte_vinculo_junto_com_atendimento(unidades, cadastros, phase):
    from app.models import ClienteFilial, Agendamento, AgendamentoServico, Comanda, ItemComanda
    from app.services.agendamento import criar_agendamento
    from app.services.persistencia import FalhaPersistencia
    s = unidades
    tables = (ClienteFilial, Agendamento, AgendamentoServico, Comanda, ItemComanda)
    baseline = [s.db.query(model).count() for model in tables]
    cliente_id = cadastros['livre'].id
    data = s.payload('barbeiro', s.a, '17:00').model_copy(update={'cliente_id': cliente_id})
    def fail_sql(conn, cursor, statement, params, context, many):
        table = 'cliente_filiais' if phase == 'vinculo' else 'comandas'
        if statement.startswith(f'INSERT INTO {table} '):
            raise IntegrityError('teste', {}, Exception('falha induzida'))
    def fail_commit(session):
        session.flush()
        raise IntegrityError('teste', {}, Exception('falha induzida'))
    target, name, callback = (s.db, 'before_commit', fail_commit) if phase == 'commit' else (s.db.get_bind(), 'before_cursor_execute', fail_sql)
    event.listen(target, name, callback)
    try:
        with pytest.raises(FalhaPersistencia): criar_agendamento(data, s.db, s.users['admin'])
    finally:
        event.remove(target, name, callback)
    assert [s.db.query(model).count() for model in tables] == baseline
    criar_agendamento(data, s.db, s.users['admin'])
    assert s.db.query(ClienteFilial).filter(ClienteFilial.cliente_id == cliente_id).count() == 1


def test_vinculo_preservado_no_cancelamento_e_reutilizado(unidades, cadastros):
    from app.models import ClienteFilial
    from app.services.agendamento import criar_agendamento, atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s = unidades
    data = s.payload('barbeiro', s.a, '17:00').model_copy(update={'cliente_id': cadastros['livre'].id})
    first = criar_agendamento(data, s.db, s.users['admin'])
    link = s.db.scalar(select(ClienteFilial).where(ClienteFilial.cliente_id == cadastros['livre'].id))
    before = (link.id, link.data_cadastro)
    atualizar_status(first.id, AgendamentoStatusUpdate(status='cancelado'), s.db, s.users['admin'])
    criar_agendamento(data, s.db, s.users['admin'])
    s.db.expire_all()
    links = s.db.scalars(select(ClienteFilial).where(ClienteFilial.cliente_id == cadastros['livre'].id)).all()
    assert len(links) == 1 and (links[0].id, links[0].data_cadastro) == before


def test_usuario_sem_vinculos_revogados_nao_pesquisa(http_app, unidades):
    from app.core.security import criar_token
    from app.models import UsuarioFilial
    s = unidades
    token = criar_token(s.users['recepcao'].id)
    link = s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == s.users['recepcao'].id))
    link.ativo = False
    s.db.commit()
    for path in ('/clientes/pesquisa', '/clientes'):
        assert asyncio.run(request(http_app, path, token))[0] == 403


def test_edicao_compartilhada_mantem_cadastro_unico_e_exige_contexto(http_app, unidades):
    from app.core.security import criar_token
    from app.models import Cliente, ClienteFilial, UsuarioFilial
    s = unidades
    token = criar_token(s.users['recepcao'].id)
    admin = criar_token(s.users['admin'].id)
    ident = s.client.id
    before = (s.db.query(Cliente).count(), s.db.query(ClienteFilial).count())
    code, result = asyncio.run(request(http_app, f'/clientes/{ident}', token, 'PATCH', {'nome': 'Nome compartilhado'}))
    assert code == 200 and result['id'] == str(ident) and 'saldo' not in result
    code, other = asyncio.run(request(http_app, f'/clientes/{ident}?filial_id={s.b.id}', admin))
    assert code == 200 and other['id'] == str(ident) and other['nome'] == 'Nome compartilhado'
    assert (s.db.query(Cliente).count(), s.db.query(ClienteFilial).count()) == before
    assert asyncio.run(request(http_app, f'/clientes/{ident}?filial_id={s.b.id}', token, 'PATCH', {'nome': 'Negado'}))[0] == 403
    link = s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == s.users['recepcao'].id))
    link.ativo = False
    s.db.commit()
    assert asyncio.run(request(http_app, f'/clientes/{ident}', token, 'PATCH', {'nome': 'Revogado'}))[0] == 403
    assert s.db.get(Cliente, ident).nome == 'Nome compartilhado'


@pytest.mark.parametrize('protected,value', [
    ('ativo', False), ('saldo', 1000), ('filial_id', '97fa517c-d7d7-4e97-a9ea-e332699918fd'),
    ('cliente_id', '97fa517c-d7d7-4e97-a9ea-e332699918fd'), ('conta_ativada', True),
    ('senha_hash', 'nao-permitir'), ('filiais', []),
])
def test_patch_nao_permite_alterar_atividade_financeiro_ou_vinculos(http_app, unidades, protected, value):
    from app.core.security import criar_token
    from app.models import ClienteFilial
    s = unidades
    token = criar_token(s.users['recepcao'].id)
    before = (s.client.nome, s.client.ativo, s.client.saldo, s.client.conta_ativada, s.client.senha_hash)
    links = {(v.id, v.filial_id) for v in s.db.scalars(select(ClienteFilial))}
    assert asyncio.run(request(http_app, f'/clientes/{s.client.id}', token, 'PATCH', {'nome': 'Nao atualizar', protected: value}))[0] == 422
    s.db.expire_all()
    assert (s.client.nome, s.client.ativo, s.client.saldo, s.client.conta_ativada, s.client.senha_hash) == before
    assert {(v.id, v.filial_id) for v in s.db.scalars(select(ClienteFilial))} == links


def test_edicao_preserva_unicidade_global_mesmo_em_outra_filial(http_app, unidades, cadastros):
    from app.core.security import criar_token
    s = unidades
    token = criar_token(s.users['recepcao'].id)
    before = s.client.telefone
    assert asyncio.run(request(http_app, f'/clientes/{s.client.id}', token, 'PATCH', {'telefone': cadastros['apenas_b'].telefone}))[0] == 409
    assert s.client.telefone == before
