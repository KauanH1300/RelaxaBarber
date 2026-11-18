from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_financeiro_servicos import caso
from test_financeiro_http import api
from test_financeiro_persistencia import data, legado, financeiro


def dados():
    from app.api.routes.estoque import ProdutoDados
    return ProdutoDados(nome='Shampoo', unidade='un', venda=True, consumo=True, custo=Decimal('3'), preco_venda=Decimal('8'), estoque_minimo=Decimal('2'))

def mov(tipo, quantidade, motivo='Teste'):
    from app.api.routes.estoque import MovimentoDados
    return MovimentoDados(tipo=tipo, quantidade=Decimal(quantidade), motivo=motivo)

def criar(db, s):
    from app.api.routes.estoque import criar
    from app.models import Usuario
    return criar(dados(), s['filial'], db, db.get(Usuario, s['atores']['admin']))

def registrar(db, s, ident, tipo, quantidade, chave=None, perfil='recepcao'):
    from app.api.routes.estoque import movimentar
    from app.models import Usuario
    return movimentar(ident, mov(tipo, quantidade), chave or uuid4(), s['filial'], db, db.get(Usuario, s['atores'][perfil]))

def test_cadastro_movimentos_replay_e_historico(runtime_pg, pg, caso):
    from app.api.routes.estoque import historico, atualizar
    from app.models import Usuario
    with Session(runtime_pg, expire_on_commit=False) as db:
        p = criar(db, caso); chave = uuid4()
        r = registrar(db, caso, p.id, 'entrada', '5', chave)
        assert registrar(db, caso, p.id, 'entrada', '5', chave).id == r.id
        assert registrar(db, caso, p.id, 'baixa', '2').saldo_apos == 3
        assert registrar(db, caso, p.id, 'ajuste', '-1').saldo_apos == 2
        assert len(historico(p.id, caso['filial'], db, db.get(Usuario, caso['atores']['recepcao']))) == 3
        with pytest.raises(HTTPException) as erro: registrar(db, caso, p.id, 'baixa', '3')
        assert erro.value.status_code == 409
        alterado = dados(); alterado.unidade = 'ml'
        with pytest.raises(HTTPException): atualizar(p.id, alterado, caso['filial'], db, db.get(Usuario, caso['atores']['admin']))
    with pg.connect() as conn:
        assert conn.scalar(text('select count(*) from movimentos_estoque')) == 3
        assert conn.scalar(text('select saldo from produtos_estoque')) == 2

def test_permissoes_e_isolamento(runtime_pg, caso):
    from app.api.routes.estoque import listar, historico
    from app.models import Usuario
    with Session(runtime_pg, expire_on_commit=False) as db:
        p = criar(db, caso)
        with pytest.raises(HTTPException) as erro:
            listar(caso['filial'], db, db.get(Usuario, caso['atores']['barbeiro']))
        assert erro.value.status_code == 403
        with pytest.raises(HTTPException) as erro:
            listar(caso['outra_filial'], db, db.get(Usuario, caso['atores']['recepcao']))
        assert erro.value.status_code == 403
        with pytest.raises(HTTPException) as erro:
            historico(p.id, caso['outra_filial'], db, db.get(Usuario, caso['atores']['admin']))
        assert erro.value.status_code == 404

def test_baixas_concorrentes_nao_negativam(runtime_pg, caso):
    from app.models.estoque import ProdutoEstoque, MovimentoEstoque
    with Session(runtime_pg, expire_on_commit=False) as db:
        p = criar(db, caso); ident = p.id
        registrar(db, caso, ident, 'entrada', '5')
    barreira = Barrier(2)
    def executar():
        with Session(runtime_pg, expire_on_commit=False) as db:
            barreira.wait()
            try:
                registrar(db, caso, ident, 'baixa', '4'); return 200
            except HTTPException as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: executar(), range(2))) == [200, 409]
    with Session(runtime_pg) as db:
        assert db.get(ProdutoEstoque, ident).saldo == 1
        assert len(db.scalars(select(MovimentoEstoque)).all()) == 2

def test_validacoes():
    from pydantic import ValidationError
    from app.api.routes.estoque import ProdutoDados
    with pytest.raises(ValidationError): mov('entrada', '-1')
    with pytest.raises(ValidationError): mov('ajuste', '0')
    with pytest.raises(ValidationError): mov('entrada', '1', '  ')
    with pytest.raises(ValidationError): ProdutoDados(nome='x', unidade='un', venda=False, consumo=False, custo=0, estoque_minimo=0)

def test_api_http_e_historico_imutavel(api, runtime_pg, pg, caso):
    from app.core.security import criar_token
    from test_seguranca_horarios import chamar
    token = criar_token(caso['atores']['admin'])
    base = f"/estoque/produtos?filial_id={caso['filial']}"
    corpo = {'nome':'Pomada', 'unidade':'un', 'venda':True, 'consumo':True, 'custo':'2.00', 'preco_venda':'4.00', 'estoque_minimo':'1'}
    status, item = chamar(api, base, method='POST', dados=corpo, token=token)
    assert status == 201 and item['saldo'] == '0.000'
    chave = uuid4()
    async def com_header(scope, receive, send):
        scope = dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(chave).encode())])
        await api(scope, receive, send)
    path = f"/estoque/produtos/{item['id']}/movimentos?filial_id={caso['filial']}"
    response = chamar(com_header, path, method='POST', dados={'tipo':'entrada','quantidade':'2','motivo':'Compra'}, token=token)
    assert response[0] == 200 and response[1]['saldo_apos'] == '2.000'
    assert chamar(com_header, path, method='POST', dados={'tipo':'entrada','quantidade':'2','motivo':'Compra'}, token=token) == response
    assert chamar(api, base, token=criar_token(caso['atores']['barbeiro']))[0] == 403
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError):
        with pg.begin() as conn:
            conn.execute(text("UPDATE movimentos_estoque SET motivo='Alterado'"))
