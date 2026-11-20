from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from test_concorrencia import data
from test_financeiro_http import api
from test_seguranca_horarios import chamar


def preparar(pg, data, saldo=3):
    from app.models import Comanda, PerfilEnum, ProdutoEstoque, Usuario
    with Session(pg, expire_on_commit=False) as db:
        admin = Usuario(nome='Admin avulsa', email=f'{uuid4()}@example.test', senha_hash='ficticio', perfil=PerfilEnum.ADMIN)
        comanda = Comanda(id=uuid4(), filial_id=data['filial'], tipo='avulsa', status='aberta', valor_total=0, comissoes_ativas=True)
        produto = ProdutoEstoque(id=uuid4(), filial_id=data['filial'], nome='Produto QA', unidade='un', venda=True, consumo=False, custo=2, preco_venda=10, estoque_minimo=0, saldo=saldo, ativo=True, comissao_padrao=20)
        db.add_all([admin, comanda, produto]); db.commit()
        return admin.id, comanda.id, produto.id


def executar(runtime_pg, data, admin, comanda, chave, **kw):
    from app.models import Usuario
    from app.services.produtos_avulsos import alterar
    with Session(runtime_pg, expire_on_commit=False) as db:
        return alterar(db, db.get(Usuario, admin), data['filial'], comanda, chave, **kw)


def test_operacoes_idempotentes_reposicao_e_snapshots(runtime_pg, pg, data):
    from app.services.comissoes_calculo import calcular
    from app.models import ItemComanda
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira, VersaoItensDesatualizada
    admin, comanda, produto = preparar(pg, data)
    chave = uuid4()
    primeiro = executar(runtime_pg, data, admin, comanda, chave, acao='adicionar', produto_id=produto, quantidade=2, profissional_id=data['user'])
    assert primeiro == executar(runtime_pg, data, admin, comanda, chave, acao='adicionar', produto_id=produto, quantidade=2, profissional_id=data['user'])
    with pytest.raises(ConflitoIdempotenciaFinanceira):
        executar(runtime_pg, data, admin, comanda, chave, acao='adicionar', produto_id=produto, quantidade=1)
    item_id = UUID(primeiro['item_id'])
    with Session(pg) as db:
        item = db.get(ItemComanda, item_id)
        comissao = calcular([item], 'nenhum', Decimal('0'), {item.id:item.comissao_percentual_snapshot}, Decimal('0'))[0]
        assert comissao.gerada == Decimal('4.00') and comissao.liberada == 0
        assert calcular([item], 'nenhum', Decimal('0'), {item.id:item.comissao_percentual_snapshot}, Decimal('10'))[0].liberada == Decimal('2.00')
    with pg.begin() as db:
        db.execute(text('UPDATE produtos_estoque SET preco_venda=99,custo=30,comissao_padrao=50 WHERE id=:id'), {'id':produto})
    chave_reduzir = uuid4()
    reducao = dict(acao='quantidade', item_id=item_id, quantidade=1, versao=primeiro['versao'])
    reduzir = executar(runtime_pg, data, admin, comanda, chave_reduzir, **reducao)
    assert reduzir == executar(runtime_pg, data, admin, comanda, chave_reduzir, **reducao)
    with pytest.raises(VersaoItensDesatualizada):
        executar(runtime_pg, data, admin, comanda, uuid4(), acao='remover', item_id=item_id, versao=primeiro['versao'])
    assert Decimal(reduzir['saldo']) == 2 and Decimal(reduzir['total']) == 10
    chave_remover = uuid4()
    removido = executar(runtime_pg, data, admin, comanda, chave_remover, acao='remover', item_id=item_id)
    assert removido == executar(runtime_pg, data, admin, comanda, chave_remover, acao='remover', item_id=item_id)
    with pg.connect() as db:
        assert db.scalar(text('SELECT saldo FROM produtos_estoque WHERE id=:id'), {'id':produto}) == 3
        assert db.scalar(text('SELECT count(*) FROM movimentos_estoque WHERE comanda_id=:id AND item_comanda_id=:item'), {'id':comanda, 'item':item_id}) == 3
        assert tuple(db.execute(text('SELECT preco_unitario,custo_snapshot,comissao_percentual_snapshot FROM itens_comanda WHERE id=:id'), {'id':item_id}).one()) == (10,2,20)
        eventos = db.execute(text('SELECT gerada,liberada,produto_id FROM eventos_comissao WHERE item_id=:id ORDER BY ordem'), {'id':item_id}).all()
        assert [tuple(e) for e in eventos] == [(4,0,produto),(2,0,produto),(0,0,produto)]
        assert db.scalar(text('SELECT count(*) FROM pagamentos_comanda WHERE comanda_id=:id'), {'id':comanda}) == 0


def test_concorrencia_estoque_e_isolamento(runtime_pg, pg, data):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    admin, primeira, produto = preparar(pg, data, saldo=1)
    segunda = uuid4()
    with pg.begin() as db:
        db.execute(text("INSERT INTO comandas (id,filial_id,tipo,status,valor_total) VALUES (:id,:filial,'avulsa','aberta',0)"), {'id':segunda,'filial':data['filial']})
    barreira = Barrier(2)
    def tentar(comanda):
        barreira.wait()
        try:
            executar(runtime_pg, data, admin, comanda, uuid4(), acao='adicionar', produto_id=produto, quantidade=1)
            return 'ok'
        except EstadoFinanceiroIncompativel:
            return 'sem saldo'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(tentar, [primeira, segunda])) == ['ok', 'sem saldo']
    outra, outro_produto = uuid4(), uuid4()
    with pg.begin() as db:
        db.execute(text("INSERT INTO filiais (id,empresa_id,nome) SELECT :id,empresa_id,'Outra' FROM filiais WHERE id=:filial"), {'id':outra,'filial':data['filial']})
        db.execute(text("INSERT INTO produtos_estoque (id,filial_id,nome,unidade,venda,consumo,custo,preco_venda,estoque_minimo,saldo) VALUES (:id,:filial,'Outro','un',true,false,1,5,0,2)"), {'id':outro_produto,'filial':outra})
    from app.services.financeiro_errors import ComandaFinanceiraNaoEncontrada
    with pytest.raises(ComandaFinanceiraNaoEncontrada):
        executar(runtime_pg, data, admin, primeira, uuid4(), acao='adicionar', produto_id=outro_produto, quantidade=1)


def test_excecao_hibrida_e_perfil(runtime_pg, pg, data):
    from app.services.financeiro_errors import AcessoFinanceiroNegado
    admin, comanda, produto = preparar(pg, data)
    with pg.begin() as db:
        db.execute(text("INSERT INTO excecoes_comissao (id,filial_id,profissional_id,produto_id,percentual,ativo,atualizado_por) VALUES (:id,:filial,:profissional,:produto,35,true,:admin)"), dict(id=uuid4(), filial=data['filial'], profissional=data['user'], produto=produto, admin=admin))
    with pytest.raises(AcessoFinanceiroNegado):
        executar(runtime_pg, data, data['user'], comanda, uuid4(), acao='adicionar', produto_id=produto, quantidade=1)
    resultado = executar(runtime_pg, data, admin, comanda, uuid4(), acao='adicionar', produto_id=produto, quantidade=1, profissional_id=data['user'])
    with pg.connect() as db:
        registro = db.execute(text('SELECT percentual,origem,produto_id FROM comissoes_item WHERE item_id=:id'), {'id':UUID(resultado['item_id'])}).one()
        assert tuple(registro) == (35, 'excecao', produto)
        evento = db.execute(text('SELECT gerada,liberada FROM eventos_comissao WHERE item_id=:id'), {'id':UUID(resultado['item_id'])}).one()
        assert tuple(evento) == (Decimal('3.50'), Decimal('0.00'))


def test_mesma_chave_concorrente_apenas_uma_baixa(runtime_pg, pg, data):
    admin, comanda, produto = preparar(pg, data, saldo=3)
    chave, barreira = uuid4(), Barrier(2)
    def tentar(_):
        barreira.wait()
        return executar(runtime_pg, data, admin, comanda, chave, acao='adicionar', produto_id=produto, quantidade=1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(tentar, range(2)))
    assert resultados[0] == resultados[1]
    with pg.connect() as db:
        assert db.scalar(text('SELECT saldo FROM produtos_estoque WHERE id=:id'), {'id':produto}) == 2
        assert db.scalar(text('SELECT count(*) FROM movimentos_estoque WHERE comanda_id=:id'), {'id':comanda}) == 1


def test_abertura_idempotente_com_controle_financeiro(runtime_pg, pg, data):
    from app.models import Usuario
    from app.services.produtos_avulsos import abrir
    admin, _, _ = preparar(pg, data)
    chave, barreira = uuid4(), Barrier(2)
    def tentativa(_):
        with Session(runtime_pg, expire_on_commit=False) as db:
            usuario = db.get(Usuario, admin)
            barreira.wait()
            return abrir(db, usuario, data['filial'], chave)
    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(tentativa, range(2)))
    assert resultados[0] == resultados[1]
    with pg.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM comandas WHERE filial_id=:filial AND chave_abertura=:chave'), dict(filial=data['filial'], chave=chave)) == 1
        assert db.scalar(text('SELECT count(*) FROM controles_financeiros_comanda WHERE comanda_id=:id'), {'id': UUID(resultados[0]['id'])}) == 1


def test_rotas_avulsas_exigem_autenticacao_e_repetem_operacao(api, runtime_pg, pg, data):
    from app.core.security import criar_token
    admin, _, produto = preparar(pg, data)
    token = criar_token(admin)
    chave = uuid4()
    async def com_chave(scope, receive, send):
        scope = dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(chave).encode())])
        await api(scope, receive, send)
    abertura = f"/comandas/avulsas?filial_id={data['filial']}"
    status, resposta = chamar(com_chave, abertura, method='POST', token=token)
    assert status == 201
    assert chamar(com_chave, abertura, method='POST', token=token) == (status, resposta)
    caminho = f"/comandas/{resposta['id']}/produtos?filial_id={data['filial']}"
    assert chamar(com_chave, caminho, method='POST', dados={'produto_id': str(produto), 'quantidade': 1}, token=token)[0] == 200
    status, conflito = chamar(com_chave, caminho, method='POST', dados={'produto_id': str(produto), 'quantidade': 2}, token=token)
    assert status == 409 and conflito['detail']['codigo'] == 'conflito_idempotencia'
    assert chamar(com_chave, abertura, method='POST')[0] == 401


def test_financeiro_avulsa_parcial_estorno_e_quitacao(runtime_pg, pg, data):
    from datetime import datetime, timedelta, timezone
    from app.models import Usuario
    from app.services.financeiro import registrar_recebimentos, registrar_estorno, consultar_situacao
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    admin, comanda, produto = preparar(pg, data)
    with pg.begin() as db:
        db.execute(text("INSERT INTO controles_financeiros_comanda (comanda_id,filial_id,registrado_por,motivo) VALUES (:comanda,:filial,:ator,'Abertura de teste')"), dict(comanda=comanda, filial=data['filial'], ator=admin))
    item = executar(runtime_pg, data, admin, comanda, uuid4(), acao='adicionar', produto_id=produto, quantidade=2, profissional_id=data['user'])
    agora = datetime.now(timezone.utc) - timedelta(seconds=2)
    def receber(valor):
        with Session(runtime_pg, expire_on_commit=False) as db:
            return registrar_recebimentos(comanda, pagamentos=[dict(valor=Decimal(valor), forma='pix', recebido_em=agora, confirmado=True)], chave_idempotencia=uuid4(), db=db, usuario=db.get(Usuario, admin), filial_id=data['filial'])
    pagamento = receber('10.00')[0]
    with pytest.raises(EstadoFinanceiroIncompativel):
        executar(runtime_pg, data, admin, comanda, uuid4(), acao='remover', item_id=UUID(item['item_id']))
    from app.schemas.cancelamento_comanda import CancelamentoComandaCreate
    from app.services.cancelamento_comanda import cancelar
    with Session(runtime_pg, expire_on_commit=False) as db, pytest.raises(EstadoFinanceiroIncompativel):
        cancelar(comanda, CancelamentoComandaCreate(versao=1, motivo='Teste', confirmado=True), uuid4(), db, db.get(Usuario, admin), data['filial'])
    with Session(runtime_pg, expire_on_commit=False) as db:
        registrar_estorno(comanda, pagamento_id=pagamento.id, valor=Decimal('2'), motivo='Correção', efetivado_em=agora + timedelta(seconds=1), chave_idempotencia=uuid4(), db=db, usuario=db.get(Usuario, admin), filial_id=data['filial'])
    with pg.connect() as db:
        assert db.scalar(text('SELECT saldo FROM produtos_estoque WHERE id=:id'), {'id':produto}) == 1
        assert db.scalar(text('SELECT liberada FROM eventos_comissao WHERE item_id=:id ORDER BY ordem DESC LIMIT 1'), {'id':UUID(item['item_id'])}) == Decimal('1.60')
    receber('12.00')
    with Session(runtime_pg) as db:
        resumo = consultar_situacao(comanda, db, db.get(Usuario, admin), data['filial'])
        assert resumo.saldo == 0 and resumo.recebido_liquido == 20 and resumo.situacao == 'fechado'
    with pg.connect() as db:
        assert db.scalar(text('SELECT status FROM comandas WHERE id=:id'), {'id':comanda}) == 'fechada'
        assert db.scalar(text('SELECT liberada FROM eventos_comissao WHERE item_id=:id ORDER BY ordem DESC LIMIT 1'), {'id':UUID(item['item_id'])}) == Decimal('4.00')


def test_cancelamento_avulsa_reposicao_idempotente(runtime_pg, pg, data):
    from app.models import Usuario
    from app.schemas.cancelamento_comanda import CancelamentoComandaCreate
    from app.services.cancelamento_comanda import cancelar
    admin, comanda, produto = preparar(pg, data)
    with pg.begin() as db:
        db.execute(text("INSERT INTO controles_financeiros_comanda (comanda_id,filial_id,registrado_por,motivo) VALUES (:comanda,:filial,:ator,'Abertura de teste')"), dict(comanda=comanda, filial=data['filial'], ator=admin))
    executar(runtime_pg, data, admin, comanda, uuid4(), acao='adicionar', produto_id=produto, quantidade=2, profissional_id=data['user'])
    with pg.begin() as db:
        db.execute(text("UPDATE comandas SET desconto_tipo='valor', desconto_valor=3, valor_total=17 WHERE id=:id"), {'id':comanda})
    chave = uuid4()
    dados = CancelamentoComandaCreate(versao=1, motivo='Cancelamento teste', confirmado=True)
    def executar_cancelamento():
        with Session(runtime_pg, expire_on_commit=False) as db:
            return cancelar(comanda, dados, chave, db, db.get(Usuario, admin), data['filial'])
    assert executar_cancelamento() == executar_cancelamento()
    with pg.connect() as db:
        assert db.scalar(text('SELECT saldo FROM produtos_estoque WHERE id=:id'), {'id':produto}) == 3
        assert db.scalar(text('SELECT count(*) FROM movimentos_estoque WHERE comanda_id=:id'), {'id':comanda}) == 2
        assert db.scalar(text('SELECT liberada FROM eventos_comissao WHERE comanda_id=:id ORDER BY ordem DESC LIMIT 1'), {'id':comanda}) == 0
    from app.services.comandas import buscar_detalhe
    from app.services.financeiro import consultar_situacao
    with Session(runtime_pg) as db:
        usuario = db.get(Usuario, admin)
        detalhe = buscar_detalhe(db, usuario, comanda, data['filial'])
        assert detalhe.status == 'cancelada' and detalhe.total == Decimal('17.00')
        assert consultar_situacao(comanda, db, usuario, data['filial']).total == Decimal('17.00')
