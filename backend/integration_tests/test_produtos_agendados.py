from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from test_financeiro_http import api
from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso
from test_seguranca_horarios import chamar


@pytest.fixture
def produto(pg, caso):
    from app.models import ProdutoEstoque
    with Session(pg, expire_on_commit=False) as db:
        db.execute(text("UPDATE comandas SET status='aberta', data_fechamento=NULL, comissoes_ativas=true WHERE id=:id"), {'id':caso['comanda']})
        p = ProdutoEstoque(id=uuid4(), filial_id=caso['filial'], nome='Produto QA', unidade='un', venda=True,
            consumo=False, custo=2, preco_venda=10, estoque_minimo=0, saldo=3, ativo=True, comissao_padrao=20)
        db.add(p); db.commit()
        return p.id


def operar(runtime_pg, caso, produto, chave, **kwargs):
    from app.models import Usuario
    from app.services.produtos_avulsos import alterar
    with Session(runtime_pg, expire_on_commit=False) as db:
        return alterar(db, db.get(Usuario, caso['atores']['recepcao']), caso['filial'], caso['comanda'], chave, **kwargs)


def test_produtos_e_servicos_na_mesma_comanda(runtime_pg, pg, caso, produto):
    from app.models import Usuario
    from app.services import alteracoes_itens, produtos_avulsos
    chave = uuid4()
    r = operar(runtime_pg, caso, produto, chave, acao='adicionar', produto_id=produto, quantidade=2, profissional_id=caso['user'])
    assert r == operar(runtime_pg, caso, produto, chave, acao='adicionar', produto_id=produto, quantidade=2, profissional_id=caso['user'])
    assert Decimal(r['total']) == Decimal('50.50') and Decimal(r['saldo']) == 1
    item = UUID(r['item_id'])
    reduzir = operar(runtime_pg, caso, produto, uuid4(), acao='quantidade', item_id=item, quantidade=1)
    assert Decimal(reduzir['total']) == Decimal('40.50') and Decimal(reduzir['saldo']) == 2
    with Session(runtime_pg) as db:
        usuario = db.get(Usuario, caso['atores']['recepcao'])
        assert len(produtos_avulsos.historico(db, usuario, caso['filial'], caso['comanda'])) == 2
        assert alteracoes_itens.historico(caso['comanda'], db, usuario, caso['filial']) == []
    resultado = operar(runtime_pg, caso, produto, uuid4(), acao='remover', item_id=item)
    assert Decimal(resultado['total']) == Decimal('30.50') and Decimal(resultado['saldo']) == 3
    with pg.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM itens_comanda WHERE comanda_id=:id AND tipo=\'servico\' AND ativo'), {'id':caso['comanda']}) == 1
        assert db.scalar(text('SELECT count(*) FROM movimentos_estoque WHERE comanda_id=:id'), {'id':caso['comanda']}) == 3
        assert db.scalar(text('SELECT liberada FROM eventos_comissao WHERE item_id=:id ORDER BY ordem DESC LIMIT 1'), {'id':item}) == 0


def test_concorrencia_e_bloqueio_apos_pagamento(runtime_pg, pg, caso, produto):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with pg.begin() as db:
        db.execute(text('UPDATE produtos_estoque SET saldo=1 WHERE id=:id'), {'id':produto})
    barreira = Barrier(2)
    def tentativa(_):
        barreira.wait()
        try:
            operar(runtime_pg, caso, produto, uuid4(), acao='adicionar', produto_id=produto, quantidade=1)
            return 'ok'
        except EstadoFinanceiroIncompativel:
            return 'sem saldo'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(tentativa, range(2))) == ['ok', 'sem saldo']
    from test_financeiro_servicos import historico
    with Session(pg) as db:
        historico(db, caso, valor=Decimal('1.00'))
    with pytest.raises(EstadoFinanceiroIncompativel):
        operar(runtime_pg, caso, produto, uuid4(), acao='adicionar', produto_id=produto, quantidade=1)


def test_rotas_permissoes_e_filial(api, pg, caso, produto):
    from app.core.security import criar_token
    chave = uuid4()
    async def app(scope, receive, send):
        await api(dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(chave).encode())]), receive, send)
    rota = f"/comandas/{caso['comanda']}/produtos?filial_id={caso['filial']}"
    body = {'produto_id': str(produto), 'quantidade': 1}
    assert chamar(app, rota, method='POST', dados=body)[0] == 401
    assert chamar(app, rota, method='POST', dados=body, token=criar_token(caso['atores']['barbeiro']))[0] in (403, 404)
    assert chamar(app, rota.replace(str(caso['filial']), str(caso['outra_filial'])), method='POST', dados=body, token=criar_token(caso['atores']['recepcao']))[0] in (403, 404)
    assert chamar(app, rota, method='POST', dados=body, token=criar_token(caso['atores']['recepcao']))[0] == 200


def test_financeiro_misto_e_comissao_proporcional(runtime_pg, pg, caso, produto):
    from datetime import datetime, timedelta, timezone
    from app.models import Usuario
    from app.services.financeiro import registrar_recebimentos, consultar_situacao
    item = operar(runtime_pg, caso, produto, uuid4(), acao='adicionar', produto_id=produto, quantidade=1, profissional_id=caso['user'])
    def receber(valor):
        with Session(runtime_pg) as db:
            return registrar_recebimentos(caso['comanda'], pagamentos=[dict(valor=Decimal(valor), forma='pix', recebido_em=datetime.now(timezone.utc)-timedelta(seconds=3), confirmado=True)], chave_idempotencia=uuid4(), db=db, usuario=db.get(Usuario, caso['atores']['recepcao']), filial_id=caso['filial'])
    receber('10.00')
    with pg.connect() as db:
        evento = db.execute(text('SELECT gerada, liberada FROM eventos_comissao WHERE item_id=:id ORDER BY ordem DESC LIMIT 1'), {'id':UUID(item['item_id'])}).one()
        assert evento.gerada == Decimal('2.00') and Decimal('0') < evento.liberada < evento.gerada
    receber('30.50')
    with Session(runtime_pg) as db:
        resumo = consultar_situacao(caso['comanda'], db, db.get(Usuario, caso['atores']['recepcao']), caso['filial'])
        assert resumo.total == Decimal('40.50') and resumo.saldo == 0 and resumo.situacao == 'fechado'
    with pg.connect() as db:
        assert db.scalar(text('SELECT liberada FROM eventos_comissao WHERE item_id=:id ORDER BY ordem DESC LIMIT 1'), {'id':UUID(item['item_id'])}) == Decimal('2.00')


def test_desconto_individual_e_geral_em_comanda_mista(runtime_pg, pg, caso, produto):
    from test_beneficios import aplicar, dados, preparar
    produto_adicionado = operar(runtime_pg, caso, produto, uuid4(), acao='adicionar', produto_id=produto, quantidade=2)
    s = caso | {'item': UUID(produto_adicionado['item_id'])}
    with Session(runtime_pg) as db:
        _, beneficio = preparar(db, s, dados(s, 'valor', '5', 'item', 1))
        resultado = aplicar(db, s, beneficio)
        assert resultado.posterior.total == Decimal('45.50')
        _, beneficio = preparar(db, s, dados(s, 'valor', '3', 'comanda', 2))
        resultado = aplicar(db, s, beneficio)
        assert resultado.posterior.total == Decimal('42.50')
    resultado = operar(runtime_pg, caso, produto, uuid4(), acao='quantidade', item_id=s['item'], quantidade=1)
    assert Decimal(resultado['total']) == Decimal('32.50') and Decimal(resultado['saldo']) == 2


def test_reducao_incompativel_com_desconto_preserva_estoque(runtime_pg, pg, caso, produto):
    from test_beneficios import aplicar, dados, preparar
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    r = operar(runtime_pg, caso, produto, uuid4(), acao='adicionar', produto_id=produto, quantidade=2)
    s = caso | {'item': UUID(r['item_id'])}
    with Session(runtime_pg) as db:
        _, beneficio = preparar(db, s, dados(s, 'valor', '15', 'item', 1))
        aplicar(db, s, beneficio)
    with pytest.raises(EntradaFinanceiraInvalida):
        operar(runtime_pg, caso, produto, uuid4(), acao='quantidade', item_id=s['item'], quantidade=1)
    with pg.connect() as db:
        assert db.scalar(text('SELECT saldo FROM produtos_estoque WHERE id=:id'), {'id':produto}) == 1
        assert db.scalar(text('SELECT quantidade FROM itens_comanda WHERE id=:id'), {'id':s['item']}) == 2
