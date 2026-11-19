"""Relatórios e falta auditada com HTTP e PostgreSQL descartável."""
import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from urllib.parse import urlencode
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text

from test_concorrencia import insert
from test_financeiro_http import api, pagar, preparar_pagamento
from test_financeiro_persistencia import data, financeiro, legado
from test_financeiro_servicos import caso
from test_financeiro_historico import estornar
from test_seguranca_horarios import chamar
from test_repasses import INICIO, FIM, pronto, usuario

FUSO = ZoneInfo('America/Recife')


def consulta(api, s, recurso='resumo', perfil='admin', **filtros):
    from app.core.security import criar_token
    hoje = datetime.now(FUSO).date()
    params = dict(filial_id=s['filial'], inicio=hoje - timedelta(days=2), fim=hoje) | filtros
    return chamar(api, f'/gerencial/{recurso}?{urlencode(params)}', token=criar_token(s['atores'][perfil]))


def test_fechamento_caixa_filtros_e_isolamento(api, pg, caso):
    ontem = datetime.now(FUSO).date() - timedelta(days=1)
    efetiva = datetime.combine(ontem, datetime.min.time(), FUSO) + timedelta(hours=16)
    # O caixa do parcial fica no dia efetivo, embora seja registrado hoje.
    status, pagamento = preparar_pagamento(pg, caso, valor='10.00', recebido_em=efetiva.isoformat())
    assert status == 200
    assert estornar(api, caso, pagamento['id'], '2.00')[0] == 200
    assert pagar(api, caso, valor='22.50')[0] == 200

    status, dados = consulta(api, caso)
    assert status == 200, dados
    i = dados['indicadores']
    assert {k: Decimal(i[k]) for k in ('faturado', 'recebido', 'estornos', 'recebido_liquido')} == {
        'faturado': Decimal('30.50'), 'recebido': Decimal('32.50'),
        'estornos': Decimal('2.00'), 'recebido_liquido': Decimal('30.50'),
    }
    assert Decimal(dados['periodos'][0]['recebido']) == Decimal('10')
    assert Decimal(dados['periodos'][0]['faturado']) == 0
    assert dados['servicos'][0]['quantidade'] == 1
    assert consulta(api, caso, busca='sem correspondência')[1]['servicos'] == []
    assert consulta(api, caso, busca='FICTICIO', ordem='faturado')[1]['servicos'] == dados['servicos']
    assert consulta(api, caso, profissional_id=caso['user'])[1]['indicadores'] == i
    assert Decimal(consulta(api, caso, profissional_id=caso['other'])[1]['indicadores']['faturado']) == 0
    assert Decimal(consulta(api, caso, filial_id=caso['outra_filial'])[1]['indicadores']['faturado']) == 0
    assert consulta(api, caso, filial_id=uuid4())[0] == 403
    assert consulta(api, caso, perfil='recepcao')[0] == 403
    assert consulta(api, caso, formato='csv', perfil='recepcao')[0] == 403
    assert consulta(api, caso, 'historico', perfil='barbeiro')[0] == 403
    assert consulta(api, caso, inicio='2026-01-02', fim='2026-01-01')[0] == 422

    status, historico = consulta(api, caso, 'historico', tipo='recebimento', tamanho=1)
    assert status == 200, historico
    assert historico['total'] == 2 and len(historico['itens']) == 1
    segunda = consulta(api, caso, 'historico', tipo='recebimento', tamanho=1, pagina=2)[1]
    assert segunda['itens'][0]['id'] != historico['itens'][0]['id']
    assert consulta(api, caso, 'historico', filial_id=caso['outra_filial'])[1]['total'] == 0
    # Exercita o SQL de todas as fontes no banco com o papel real de runtime.
    assert consulta(api, caso, 'historico')[1]['total'] >= 4

    with pg.begin() as conn:
        insert(conn, caso, day=ontem, status='concluido', professional=caso['other'])
    assert consulta(api, caso)[1]['profissionais'][0]['id'] == str(caso['user'])
    assert consulta(api, caso, ordem_equipe='concluidos')[1]['profissionais'][0]['id'] == str(caso['other'])
    assert consulta(api, caso, ordem_equipe='invalida')[0] == 422


def test_comissoes_por_origem_e_repasse_liquido(api, runtime_pg, pronto):
    from sqlalchemy.orm import Session
    from uuid import UUID
    from app.services import repasses

    s = pronto
    with Session(runtime_pg, expire_on_commit=False) as db:
        ator = usuario(db, s)
        fechamento = UUID(repasses.fechar(db, ator, s['filial'], s['user'], INICIO, FIM, uuid4())['id'])
        p = repasses.pagar(db, ator, s['filial'], s['user'], fechamento, Decimal('1'), 'pix',
                           datetime.now(timezone.utc) - timedelta(seconds=5), uuid4())
        repasses.estornar(db, ator, s['filial'], s['user'], fechamento, UUID(p['id']),
                          Decimal('0.50'), 'Correção', uuid4())
    status, dados = consulta(api, s, inicio=INICIO, fim=FIM)
    assert status == 200, dados
    esperado = dict(gerada=Decimal('6.10'), liberada=Decimal('2'), elegivel=Decimal('0'), paga=Decimal('0.50'))
    assert {k: Decimal(v) for k, v in dados['comissoes'].items()} == esperado
    assert consulta(api, s, inicio=INICIO, fim=FIM, profissional_id=s['other'])[1]['comissoes'] == dict.fromkeys(esperado, '0.00')


def test_csv_mesma_apuracao_e_escape(pg, caso, api):
    from app.core.security import criar_token

    with pg.begin() as conn:
        conn.execute(text("UPDATE itens_comanda SET descricao='  =1+1' WHERE comanda_id=:comanda"), caso)
    assert pagar(api, caso)[0] == 200
    hoje = datetime.now(FUSO).date()
    params = dict(filial_id=str(caso['filial']), inicio=str(hoje - timedelta(days=1)), fim=str(hoje), busca='=1')
    token = criar_token(caso['atores']['admin'])
    status, headers, corpo = chamar(api, '/gerencial/resumo?' + urlencode(params | {'formato': 'csv'}),
                                    token=token, resposta_bruta=True)
    assert status == 200, corpo
    assert headers[b'content-type'].startswith(b'text/csv')
    linhas = list(csv.reader(StringIO(corpo.decode('utf-8-sig')), delimiter=';'))
    assert any(linha and linha[0] == 'faturado' and Decimal(linha[1]) == Decimal('30.50') for linha in linhas)
    assert any("'  =1+1" in linha for linha in linhas)


def test_falta_confirmada_sem_recebimentos_e_com_auditoria(api, pg, runtime_pg, caso, monkeypatch):
    from app.core.security import criar_token
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models import Comanda, ItemComanda
    from app.services import agendamento, comissoes

    data_reserva = date(2026, 9, 1)
    with pg.begin() as conn:
        reserva = insert(conn, caso, day=data_reserva)
        comanda = uuid4()
        conn.execute(text("""INSERT INTO comandas(id,filial_id,agendamento_id,cliente_id,barbeiro_id,status,valor_total,comissoes_ativas)
            VALUES (:id,:filial,:reserva,:client,:user,'pendente',30.50,true)"""),
            caso | dict(id=comanda, reserva=reserva))
        conn.execute(text("""INSERT INTO itens_comanda(id,comanda_id,tipo,descricao,quantidade,preco_unitario,servico_id)
            VALUES (:id,:comanda,'servico','Corte',1,30.50,:service)"""), caso | dict(id=uuid4(), comanda=comanda))
        versao = conn.scalar(text('SELECT atualizado_em FROM agendamentos WHERE id=:id'), {'id': reserva})
    with Session(runtime_pg) as db:
        c = db.get(Comanda, comanda)
        item = db.scalar(select(ItemComanda).where(ItemComanda.comanda_id == comanda))
        comissoes.fixar(db, c, item, caso['user'])
        comissoes.registrar(db, c, Decimal('0.00'), 'inclusao', caso['atores']['admin'])
        db.commit()

    path = f"/agendamentos/{reserva}/status?filial_id={caso['filial']}"
    dados = dict(status='nao_compareceu', atualizado_em_esperado=versao.isoformat(),
                 falta_motivo='  Não se apresentou  ', confirmado=True)

    def marcar(perfil='recepcao', **mudancas):
        return chamar(api, path, method='PATCH', dados=dados | mudancas, token=criar_token(caso['atores'][perfil]))

    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime(2026, 9, 1, 9, 20, tzinfo=FUSO))
    assert marcar()[0] == 409
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime(2026, 9, 1, 9, 31, tzinfo=FUSO))
    assert marcar('barbeiro')[0] == 403
    assert marcar(confirmado=False)[0] == 422
    assert marcar(atualizado_em_esperado=datetime(2026, 8, 1, tzinfo=timezone.utc).isoformat())[0] == 409
    status, ag = marcar()
    assert status == 200, ag
    assert ag['status'] == 'nao_compareceu'
    assert ag['falta_motivo'] == 'Não se apresentou'
    assert ag['falta_registrada_por'] == str(caso['atores']['recepcao'])
    assert ag['cancelado_em'] is None
    assert marcar()[0] == 409
    with pg.begin() as conn:
        assert conn.scalar(text('SELECT status FROM comandas WHERE id=:id'), {'id': comanda}) == 'cancelada'
        gerada, liberada, operacao = conn.execute(text("""SELECT gerada, liberada, operacao
            FROM eventos_comissao WHERE comanda_id=:id ORDER BY ordem DESC LIMIT 1"""), {'id': comanda}).one()
        assert (gerada, liberada, operacao) == (Decimal('0'), Decimal('0'), 'nao_comparecimento')
        for tabela in ('pagamentos_comanda', 'movimentos_estoque'):
            assert conn.scalar(text(f'SELECT count(*) FROM {tabela} WHERE comanda_id=:id'), {'id': comanda}) == 0

    filtros = dict(inicio=data_reserva, fim=data_reserva)
    status, resumo = consulta(api, caso, **filtros)
    assert status == 200, resumo
    assert resumo['indicadores']['faltas'] == 1 and resumo['indicadores']['cancelados'] == 0
    assert consulta(api, caso, 'historico', tipo='nao_comparecimento', **filtros)[1]['total'] == 1
    with pg.begin() as conn:
        insert(conn, caso, day=data_reserva)

