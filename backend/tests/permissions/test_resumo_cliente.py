"""Resumos são leituras com escopo explícito, sem pagamentos inferidos."""
import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from test_filiais import unidades, http_app, request


@pytest.fixture
def historico(unidades):
    from app.models import AgendamentoServico, Comanda, ItemComanda
    s = unidades
    for key, booking in s.bookings.items():
        booking.status = 'cancelado' if key == ('itinerante', 'A') else 'concluido'
    # Vários serviços/itens e valores altos nunca alteram contagens/dinheiro.
    appointment = s.bookings[('barbeiro', 'A')]
    command = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == appointment.id))
    command.valor_total = 99999
    command.status = 'fechada'
    s.client.saldo = 777
    for _ in range(3):
        s.db.add(AgendamentoServico(agendamento_id=appointment.id, servico_id=s.service.id, preco=500, tempo_estimado=1))
        s.db.add(ItemComanda(comanda_id=command.id, tipo='servico', descricao='Sem pagamento', quantidade=5, preco_unitario=500))
    s.db.commit()
    return s


def consultar(app, s, role, endpoint='resumo', **params):
    from app.core.security import criar_token
    query = '&'.join(f'{k}={v}' for k, v in params.items())
    return asyncio.run(request(app, f'/clientes/{s.client.id}/{endpoint}?{query}', criar_token(s.users[role].id)))


@pytest.mark.parametrize('role,total,scope', [
    ('admin', 4, 'todos'), ('recepcao', 2, 'todos'),
    ('barbeiro_chefe', 2, 'todos'), ('barbeiro', 1, 'proprio'), ('itinerante', 1, 'proprio'),
])
def test_contagens_nao_duplicam_e_respeitam_perfil(http_app, historico, role, total, scope):
    s = historico
    code, result = consultar(http_app, s, role)
    assert code == 200
    assert result['atendimentos_concluidos'] == total
    assert result['escopo_profissional'] == scope
    assert result['parcial'] is (role != 'admin')
    assert result['escopo_filiais'] == ('empresa' if role == 'admin' else 'filiais_autorizadas')
    assert total == sum(f['atendimentos_concluidos'] for f in result['filiais'])
    if role not in ('admin', 'itinerante'):
        assert [f['filial_id'] for f in result['filiais']] == [str(s.a.id)]
    assert 'total_gasto' not in result and 'saldo' not in str(result)


def test_financeiro_sem_pagamentos_e_sempre_null(http_app, historico):
    code, result = consultar(http_app, historico, 'admin', 'resumo-financeiro')
    assert code == 200 and result['financeiro_disponivel'] is False
    assert result['total_gasto'] is None
    assert result['atendimentos_concluidos'] == 4
    assert len(result['filiais']) == 2
    assert all(f['total_gasto'] is None for f in result['filiais'])


@pytest.mark.parametrize('role', ['recepcao', 'barbeiro', 'barbeiro_chefe', 'itinerante'])
def test_financeiro_nao_amplia_permissoes(http_app, historico, role):
    assert consultar(http_app, historico, role, 'resumo-financeiro')[0] == 403


def test_multifilial_consolida_apenas_autorizadas_sem_depender_da_unidade_ativa(http_app, historico):
    from app.models import UsuarioFilial
    s = historico
    s.db.add(UsuarioFilial(usuario=s.users['recepcao'], filial=s.b))
    s.db.commit()
    for unidade in (s.a, s.b):
        code, result = consultar(http_app, s, 'recepcao', filial_id=unidade.id)
        assert code == 200 and result['atendimentos_concluidos'] == 4
        assert result['parcial']  # Não revela se o usuário conhece todas as filiais.
    assert consultar(http_app, s, 'barbeiro', filial_id=s.b.id)[0] == 403


def test_revogacao_restringe_resumo_imediatamente(http_app, historico):
    from app.models import UsuarioFilial
    s = historico
    link = s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == s.users['itinerante'].id, UsuarioFilial.filial_id == s.b.id))
    assert consultar(http_app, s, 'itinerante')[1]['atendimentos_concluidos'] == 1
    link.ativo = False
    s.db.commit()
    result = consultar(http_app, s, 'itinerante')[1]
    assert result['atendimentos_concluidos'] == 0
    assert [f['filial_id'] for f in result['filiais']] == [str(s.a.id)]
    s.db.query(UsuarioFilial).filter_by(usuario_id=s.users['itinerante'].id).update({'ativo': False})
    s.db.commit()
    assert consultar(http_app, s, 'itinerante')[0] == 403


def test_historico_inativo_so_admin(http_app, historico):
    s = historico
    s.b.ativa = False
    s.client.ativo = False  # Histórico permanece consultável.
    s.db.commit()
    assert consultar(http_app, s, 'admin')[1]['atendimentos_concluidos'] == 4
    result = consultar(http_app, s, 'itinerante')[1]
    assert result['atendimentos_concluidos'] == 0 and len(result['filiais']) == 1


@pytest.mark.parametrize('endpoint', ['resumo', 'resumo-financeiro'])
def test_uuid_inexistente_404_e_cliente_sem_historico_zero(http_app, historico, endpoint):
    from app.core.security import criar_token
    from app.models import Cliente, ClienteFilial
    s = historico
    token = criar_token(s.users['admin'].id)
    assert asyncio.run(request(http_app, f'/clientes/{uuid4()}/{endpoint}', token))[0] == 404
    client = Cliente(nome='Sem histórico', telefone='000099')
    s.db.add(client)
    s.db.flush()
    s.db.add(ClienteFilial(cliente=client, filial=s.a))
    s.db.commit()
    code, result = asyncio.run(request(http_app, f'/clientes/{client.id}/{endpoint}', token))
    assert code == 200 and result['atendimentos_concluidos'] == 0
    assert result['filiais'][0]['atendimentos_concluidos'] == 0
    if endpoint == 'resumo-financeiro':
        assert result['total_gasto'] is None


@pytest.mark.parametrize('role', ['recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_cliente_apenas_em_outra_unidade_e_oculto_por_uuid(http_app, historico, role):
    from app.core.security import criar_token
    from app.models import Cliente, ClienteFilial
    s = historico
    cliente = Cliente(nome='Somente B', telefone='000098')
    s.db.add(cliente)
    s.db.flush()
    s.db.add(ClienteFilial(cliente=cliente, filial=s.b))
    s.db.commit()
    token = criar_token(s.users[role].id)
    assert asyncio.run(request(http_app, f'/clientes/{cliente.id}/resumo', token))[0] == 404
    assert asyncio.run(request(http_app, f'/clientes/{cliente.id}/resumo?filial_id={s.b.id}', token))[0] == 403
    assert asyncio.run(request(http_app, f'/clientes/{cliente.id}/resumo-financeiro', token))[0] == 403
    # Cliente compartilhado, mas não vinculado à unidade explicitamente aberta.
    link = s.db.query(ClienteFilial).filter_by(cliente_id=s.client.id, filial_id=s.a.id).one()
    s.db.delete(link)
    s.db.commit()
    assert consultar(http_app, s, role, filial_id=s.a.id)[0] == 404


@pytest.mark.parametrize('status,total', [('pendente', 0), ('aguardando', 0), ('em_atendimento', 0), ('cancelado', 0), ('concluido', 1)])
def test_somente_concluidos_contam(http_app, unidades, status, total):
    s = unidades
    for booking in s.bookings.values():
        booking.status = 'cancelado'
    s.bookings[('barbeiro', 'A')].status = status
    s.db.commit()
    assert consultar(http_app, s, 'admin')[1]['atendimentos_concluidos'] == total


def test_empresa_inativa_e_perfil_rebaixado_nao_vazam_resumos(http_app, historico):
    s = historico
    # Mesmo objeto/JWT previamente ADMIN precisa perder o acesso financeiro.
    from app.core.security import criar_token
    token = criar_token(s.users['admin'].id)
    s.users['admin'].perfil = 'recepcao'
    s.db.commit()
    assert asyncio.run(request(http_app, f'/clientes/{s.client.id}/resumo-financeiro', token))[0] == 403
    assert consultar(http_app, s, 'admin')[0] == 403  # Sem vínculos.
    s.a.empresa.ativa = False
    s.db.commit()
    assert consultar(http_app, s, 'recepcao')[0] == 403


def test_contrato_nao_aceita_dinheiro_enquanto_indisponivel(isolated_runtime):
    from app.schemas.resumo_cliente import ResumoFinanceiroCliente
    from pydantic import ValidationError
    fields = dict(cliente_id=uuid4(), escopo_filiais='empresa', escopo_profissional='todos', parcial=False, atendimentos_concluidos=0, filiais=[])
    with pytest.raises(ValidationError):
        ResumoFinanceiroCliente(**fields, total_gasto=0)
    with pytest.raises(ValidationError):
        ResumoFinanceiroCliente(**fields, financeiro_disponivel=True)

    with pytest.raises(ValidationError):
        ResumoFinanceiroCliente(**(fields | {'filiais': [dict(filial_id=uuid4(), filial_nome='Teste', atendimentos_concluidos=0, total_gasto=12)]}))
