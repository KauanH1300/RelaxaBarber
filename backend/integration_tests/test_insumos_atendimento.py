from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from decimal import Decimal
from threading import Barrier
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from test_complementos_agenda import criar_recepcao, requisitar
from test_concorrencia import data
from test_contexto_filiais import duas_filiais, payload
from test_financeiro_http import api


def produtos(pg, s, filial=None):
    from app.models.estoque import ProdutoEstoque
    with Session(pg) as db, db.begin():
        itens = [ProdutoEstoque(filial_id=filial or s['filial'], nome=nome, unidade='ml',
            venda=False, consumo=True, custo=0, saldo=saldo, estoque_minimo=0)
            for nome, saldo in [('Creme', Decimal('1.500')), ('Loção', Decimal('0'))]]
        db.add_all(itens)
        db.flush()
        return [i.id for i in itens]


def receita(api, s, principal, secundario, *, filial=None, ator=None, servico=None):
    return requisitar(api, f"/servicos/{servico or s['service']}/insumos", ator or s['admin'],
        method='PUT', filial_id=filial or s['filial'], dados=[
            {'produto_id': str(principal), 'quantidade': '1.250'},
            {'produto_id': str(secundario), 'quantidade': '0.125'},
        ])


def agendar(api, s, hora=9, extra=None):
    dados = payload(s, s['filial']).model_copy(update={'hora_inicio': time(hora)}).model_dump(mode='json')
    if extra:
        dados['servicos'].append({'servico_id': str(extra)})
    codigo, resposta = requisitar(api, '/agendamentos', s['admin'], method='POST', dados=dados)
    assert codigo == 201, resposta
    return resposta


def status(api, s, reserva, alvo, **campos):
    return requisitar(api, f"/agendamentos/{reserva['id']}/status", s['admin'], method='PATCH',
        filial_id=s['filial'], dados={'status': alvo, **campos})


@pytest.mark.parametrize('multisservico', [False, True])
def test_concluir_uma_vez_com_divergencia_sem_editar_comanda(api, pg, duas_filiais, multisservico):
    from app.models import ProdutoEstoque, Servico
    s = duas_filiais
    p, q = produtos(pg, s)
    with Session(pg) as db, db.begin():
        db.get(ProdutoEstoque, p).estoque_minimo = Decimal('0.250')
    rota_alertas = '/estoque/alertas'
    assert {a['id'] for a in requisitar(api, rota_alertas, s['admin'], filial_id=s['filial'])[1]} == {str(q)}
    assert receita(api, s, p, q)[0] == 200
    extra = None
    if multisservico:
        with Session(pg) as db, db.begin():
            servico = Servico(nome='Complemento', preco=10, tempo_estimado=10, comissao_padrao=0)
            db.add(servico); db.flush()
            extra = servico.id
        assert receita(api, s, p, q, servico=extra)[0] == 200
    reserva = agendar(api, s, extra=extra)
    assert status(api, s, reserva, 'em_atendimento')[0] == 200
    parametros = {'id': UUID(reserva['id'])}
    with pg.connect() as conn:
        antes = conn.execute(text('SELECT status,valor_total,updated_at FROM comandas WHERE agendamento_id=:id'), parametros).one()
        eventos = conn.scalar(text('SELECT count(*) FROM eventos_comissao'))
    codigo, concluido = status(api, s, reserva, 'concluido')
    assert codigo == 200, concluido
    assert status(api, s, reserva, 'concluido') == (200, concluido)
    assert {a['id'] for a in requisitar(api, rota_alertas, s['admin'], filial_id=s['filial'])[1]} == {str(p), str(q)}
    assert status(api, s, reserva, 'em_atendimento')[0] == 400
    esperados = {str(q): Decimal('0.250' if multisservico else '0.125')}
    if multisservico:
        esperados[str(p)] = Decimal('1.000')
    assert {x['produto_id']: Decimal(x['nao_baixada']) for x in concluido['divergencias_insumos']} == esperados
    with pg.connect() as conn:
        assert conn.execute(text('SELECT status,valor_total,updated_at FROM comandas WHERE agendamento_id=:id'), parametros).one() == antes
        assert conn.scalar(text('SELECT count(*) FROM eventos_comissao')) == eventos
        assert conn.scalar(text('SELECT count(*) FROM consumos_atendimento')) == 2
        linha = conn.execute(text('SELECT quantidade,saldo_apos,comanda_id FROM movimentos_estoque')).one()
        assert linha == ((Decimal('-1.500'), 0, None) if multisservico else (Decimal('-1.250'), Decimal('0.250'), None))


def test_receita_autorizacao_filial_e_sem_baixa_em_cancelamento_ou_falta(api, pg, duas_filiais, monkeypatch):
    from app.services import agendamento

    s = duas_filiais
    p, q = produtos(pg, s)
    outro, _ = produtos(pg, s, s['second'])
    recepcao = criar_recepcao(pg, s)
    assert receita(api, s, p, q, ator=recepcao)[0] == 403
    assert receita(api, s, p, q, ator=s['user'])[0] == 403
    assert receita(api, s, outro, q)[0] == 422
    assert receita(api, s, p, p)[0] == 422
    assert receita(api, s, p, q)[0] == 200
    assert requisitar(api, f"/servicos/{s['service']}/insumos", s['admin'], filial_id=s['second']) == (200, [])
    a, b = agendar(api, s), agendar(api, s, 11)
    assert status(api, s, a, 'cancelado', atualizado_em_esperado=a['atualizado_em'],
                  confirmado=True, motivo_cancelamento='Cancelamento de teste')[0] == 200
    from datetime import datetime
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime.combine(date(2099, 1, 1), time(13), agendamento.FUSO_BARBEARIA))
    assert status(api, s, b, 'nao_compareceu', atualizado_em_esperado=b['atualizado_em'],
                  confirmado=True, falta_motivo='Falta de teste')[0] == 200
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM consumos_atendimento')) == 0
        assert conn.scalar(text('SELECT count(*) FROM movimentos_estoque')) == 0
        for tabela in ('insumos_servico','consumos_atendimento'):
            for papel in ('anon','authenticated','service_role'):
                assert not conn.scalar(text("SELECT has_table_privilege(:p,:t,'SELECT,INSERT,UPDATE,DELETE')"),
                                       {'p':papel,'t':'public.' + tabela})


def test_duas_conclusoes_concorrentes_consumem_ate_o_saldo(api, pg, duas_filiais):
    s = duas_filiais
    p, q = produtos(pg, s)
    with pg.begin() as conn:
        conn.execute(text('UPDATE produtos_estoque SET saldo=0.200 WHERE id=:id'), {'id':q})
    assert receita(api, s, p, q)[0] == 200
    reservas = [agendar(api, s, h) for h in (9, 11)]
    for r in reservas:
        assert status(api, s, r, 'em_atendimento')[0] == 200
    pronta = Barrier(2, timeout=6)
    def concluir(r):
        pronta.wait()
        return status(api, s, r, 'concluido')
    with ThreadPoolExecutor(max_workers=2) as pool:
        respostas = list(pool.map(concluir, reservas))
    assert [r[0] for r in respostas] == [200, 200], respostas
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT sum(saldo) FROM produtos_estoque')) == 0
        assert conn.scalar(text('SELECT count(*) FROM consumos_atendimento')) == 4
        assert conn.scalar(text('SELECT sum(baixada) FROM consumos_atendimento')) == Decimal('1.700')
        assert conn.scalar(text('SELECT sum(prevista-baixada) FROM consumos_atendimento')) == Decimal('1.050')
