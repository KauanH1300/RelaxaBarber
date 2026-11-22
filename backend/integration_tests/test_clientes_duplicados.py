from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.util import load_python_file
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from test_complementos_agenda import api, criar_recepcao, data, duas_filiais, requisitar
from test_reserva_publica import agenda, payload
from test_troca_email_cliente import entrega


def cadastrar(api, s, nome, telefone, *, filial=None, email=None):
    status, cliente = requisitar(api, '/clientes', s['admin'], method='POST', dados={
        'nome': nome, 'telefone': telefone, 'email': email, 'filial_id': str(filial or s['filial']),
    })
    assert status == 201, cliente
    return cliente['id']


def listar(api, ator, filial, busca=''):
    status, clientes = requisitar(api, '/clientes', ator, filial_id=filial, busca=busca)
    assert status == 200, clientes
    return {c['id']: c['possivel_duplicidade'] for c in clientes}


def test_sinalizacao_por_filial_perfil_e_telefone_normalizado(api, pg, duas_filiais):
    s = duas_filiais
    recepcao = criar_recepcao(pg, s)
    local = cadastrar(api, s, 'Local', '(81) 99999-1234')
    remoto = cadastrar(api, s, 'Outra unidade', '(81) 99999-1234', filial=s['second'])
    assert listar(api, recepcao, s['filial'], '+5581999991234') == {local: False}
    assert listar(api, s['admin'], s['second'], '81999991234') == {remoto: False}
    assert requisitar(api, '/clientes', recepcao, filial_id=s['second'])[0] == 403
    coincidencias = '/clientes/coincidencias'
    filtros = dict(filial_id=s['filial'], telefone='+5581999991234')
    status, encontrados = requisitar(api, coincidencias, recepcao, **filtros)
    assert status == 200 and encontrados == [{'id': local, 'nome': 'Local', 'telefone': '(81) 99999-1234'}]
    assert requisitar(api, coincidencias, recepcao, ignorar_id=local, **filtros) == (200, [])
    assert requisitar(api, coincidencias, recepcao, **(filtros | {'filial_id': s['second']}))[0] == 403

    segundo = cadastrar(api, s, 'Outro local', '+55 81 99999-1234')
    assert listar(api, recepcao, s['filial'], '81999991234') == {local: True, segundo: True}
    assert listar(api, s['user'], s['filial'], '81999991234') == {local: False, segundo: False}
    assert listar(api, s['admin'], s['second'], '81999991234') == {remoto: False}
    duplicidades = '/clientes/duplicidades'
    assert requisitar(api, duplicidades, s['user'], filial_id=s['filial'])[0] == 403
    assert requisitar(api, duplicidades, recepcao, filial_id=s['second'])[0] == 403
    assert requisitar(api, duplicidades, s['admin'], filial_id=s['second']) == (200, [])
    legado = cadastrar(api, s, 'Legado', 'sem número')
    outro_legado = cadastrar(api, s, 'Outro legado', 'sem número')
    assert listar(api, recepcao, s['filial'], 'sem número') == {legado: False, outro_legado: False}

    status, _ = requisitar(api, f'/clientes/{segundo}', recepcao, filial_id=s['filial'], method='PATCH',
                           dados={'telefone': '81999992345'})
    assert status == 200
    assert listar(api, recepcao, s['filial'], '81999991234') == {local: False}


def test_portal_independente_com_mesmo_email_de_contato_e_telefone(
    api, runtime_pg, agenda, duas_filiais, entrega,
):
    from app.models import Agendamento, Cliente, ContaPortalCliente
    from app.schemas.portal_cliente import CadastroPortal, ConfirmarPortal, LoginPortal
    from app.services import minha_agenda, portal_cliente as portal, reserva_publica

    s = duas_filiais
    email = 'novo@example.com'
    presencial = cadastrar(api, s, 'Cliente presencial', '(81) 99999-1234', email=email)
    dados = CadastroPortal(nome='Conta própria', telefone='81999991234', email=email,
                           senha='Senha-ficticia-duplicidade-123')
    ip = '127.0.0.4'
    with Session(runtime_pg) as db:
        solicitacao = portal.solicitar(db, dados, ip, 'cadastro')
        assert portal.conta_por_email(db, email) is None
        confirmar = ConfirmarPortal(solicitacao_id=solicitacao['solicitacao_id'], codigo=entrega[-1][1])
        errado = '000000' if confirmar.codigo != '000000' else '999999'
        with pytest.raises(portal.PortalFalha, match='Código inválido'):
            portal.confirmar(db, confirmar.model_copy(update={'codigo': errado}), ip, 'cadastro')
        portal.confirmar(db, confirmar, ip, 'cadastro')
        token = portal.login(db, LoginPortal(email=email, senha=dados.senha), ip)
        online = portal.autenticar(db, token).id
        assert str(online) != presencial
        assert db.get(ContaPortalCliente, online).email_confirmado == email
        original = db.get(Cliente, UUID(presencial))
        assert original.email == email and original.telefone == '(81) 99999-1234' and not original.conta_ativada

    assert listar(api, s['admin'], s['filial'], '81999991234') == {presencial: False}
    status, interna = requisitar(api, '/agendamentos', s['admin'], method='POST', dados={
        'cliente_id': presencial, 'barbeiro_id': str(s['user']), 'filial_id': str(s['filial']),
        'data': '2099-05-20', 'hora_inicio': '10:00', 'servicos': [{'servico_id': str(s['service'])}],
    })
    assert status == 201, interna
    with Session(runtime_pg) as db:
        assert not minha_agenda.listar(db, token)
        pedido = payload(agenda)
        reserva = reserva_publica.confirmar(db, pedido, token)
        assert reserva_publica.confirmar(db, pedido, token).id == reserva.id
        assert [a.id for a in minha_agenda.listar(db, token)] == [reserva.id]
        assert {str(cliente_id) for cliente_id in db.scalars(select(Agendamento.cliente_id))} == {
            presencial, str(online),
        }
    assert listar(api, s['admin'], s['filial'], '81999991234') == {presencial: True, str(online): True}
    outro = cadastrar(api, s, 'Atendimento anterior', '(11) 99999-1234')
    outro_par = cadastrar(api, s, 'Outro presencial', '5511999991234')
    status, grupos = requisitar(api, '/clientes/duplicidades', s['admin'], filial_id=s['filial'])
    assert status == 200
    assert [(g['telefone_normalizado'], g['inclui_presencial_e_online']) for g in grupos] == [
        ('5581999991234', True), ('5511999991234', False),
    ]
    assert [c['id'] for c in grupos[0]['clientes']] == [presencial, str(online)]
    assert {c['id'] for c in grupos[1]['clientes']} == {outro, outro_par}
    assert all(set(c) == {'id', 'nome', 'telefone', 'conta_ativada'} for g in grupos for c in g['clientes'])


def test_migracao_preserva_legados_e_bloqueia_downgrade_com_contatos_compartilhados(pg):
    versoes = Path(__file__).resolve().parents[1] / 'alembic' / 'versions'
    migracao = load_python_file(str(versoes), '2eb4a16d930c_contatos_clientes_compartilhados.py')
    with pg.begin() as db:
        with Operations.context(MigrationContext.configure(db)):
            migracao.downgrade()
            for telefone in ('(81) 99999-1234', 'sem número'):
                db.execute(text("""INSERT INTO clientes (id,nome,telefone,conta_ativada,saldo,ativo)
                    VALUES (:id,'Legado',:telefone,false,0,true)"""), {'id': uuid4(), 'telefone': telefone})
            migracao.upgrade()
            assert dict(db.execute(text('SELECT telefone, telefone_normalizado FROM clientes')).tuples().all()) == {
                '(81) 99999-1234': '5581999991234', 'sem número': None,
            }
            indices = {i['name']: i for i in inspect(db).get_indexes('clientes', schema='public')}
            assert not indices['ix_clientes_telefone_normalizado']['unique']
            assert 'ix_clientes_telefone' not in indices
            db.execute(text("""INSERT INTO clientes (id,nome,telefone,conta_ativada,saldo,ativo)
                VALUES (:id,'Outro','(81) 99999-1234',false,0,true)"""), {'id': uuid4()})
            with pytest.raises(DBAPIError, match='contatos compartilhados'), db.begin_nested():
                migracao.downgrade()
            assert db.scalar(text("SELECT count(*) FROM clientes WHERE telefone_normalizado='5581999991234'")) == 2
