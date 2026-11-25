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


def test_cadastro_recupera_mesma_chave_concorrente_e_respeita_filial(runtime_pg, caso):
    from app.api.routes.estoque import criar
    from app.models import Usuario
    from app.models.estoque import ProdutoEstoque
    chave = uuid4()
    barreira = Barrier(2, timeout=8)

    def executar(_):
        with Session(runtime_pg) as db:
            ator = db.get(Usuario, caso['atores']['admin'])
            barreira.wait()
            return criar(dados(), caso['filial'], db, ator, chave).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        primeiro, segundo = pool.map(executar, range(2))
    assert primeiro == segundo
    with Session(runtime_pg) as db:
        recepcao = db.get(Usuario, caso['atores']['recepcao'])
        with pytest.raises(HTTPException) as erro:
            criar(dados(), caso['filial'], db, recepcao, chave)
        assert erro.value.status_code == 403
        admin = db.get(Usuario, caso['atores']['admin'])
        assert db.query(ProdutoEstoque).count() == 1
        assert criar(dados(), caso['outra_filial'], db, admin, chave).id != primeiro

def test_baixas_concorrentes_nao_negativam(runtime_pg, caso):
    from app.models.estoque import ProdutoEstoque, MovimentoEstoque
    from app.api.routes.estoque import listar_alertas
    from app.models import Usuario
    from fastapi import Response
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
        alertas = listar_alertas(Response(), caso['filial'], db, db.get(Usuario, caso['atores']['recepcao']))
        assert [(a['id'], a['saldo']) for a in alertas] == [(ident, Decimal('1'))]


def test_alertas_estoque_refletem_saldo_minimo_atividade_e_permissoes(api, runtime_pg, caso):
    from app.api.routes.estoque import atualizar
    from app.core.security import criar_token
    from app.models import Usuario
    from test_seguranca_horarios import chamar

    def alertas(perfil='recepcao', filial=None):
        return chamar(api, f"/estoque/alertas?filial_id={filial or caso['filial']}",
                      token=criar_token(caso['atores'][perfil]))

    with Session(runtime_pg, expire_on_commit=False) as db:
        item = criar(db, caso)
        ident = str(item.id)
        registrar(db, caso, item.id, 'entrada', '5')
        assert alertas() == (200, [])
        chave = uuid4()
        movimento = registrar(db, caso, item.id, 'baixa', '3', chave)
        assert registrar(db, caso, item.id, 'baixa', '3', chave).id == movimento.id
        esperado = {'id': ident, 'nome': 'Shampoo', 'unidade': 'un', 'saldo': '2.000', 'estoque_minimo': '2.000'}
        assert alertas() == alertas('admin') == (200, [esperado])
        assert alertas('barbeiro')[0] == 403
        assert alertas(filial=caso['outra_filial'])[0] == 403
        assert alertas('admin', caso['outra_filial']) == (200, [])
        registrar(db, caso, item.id, 'ajuste', '1')
        assert alertas() == (200, [])
        admin = db.get(Usuario, caso['atores']['admin'])
        novo_minimo = dados().model_copy(update={'estoque_minimo': Decimal('3')})
        atualizar(item.id, novo_minimo, caso['filial'], db, admin)
        assert alertas() == (200, [esperado | {'saldo': '3.000', 'estoque_minimo': '3.000'}])
        atualizar(item.id, novo_minimo.model_copy(update={'ativo': False}), caso['filial'], db, admin)
        assert alertas() == (200, [])

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

@pytest.mark.parametrize('tabela', ['produtos_estoque', 'movimentos_estoque'])
@pytest.mark.parametrize('role', ['anon', 'authenticated', 'service_role'])
def test_papeis_supabase_nao_acessam_estoque(pg, tabela, role):
    from runtime_roles import engine_login
    from sqlalchemy.exc import ProgrammingError
    with pg.connect() as conn:
        for priv in ('SELECT', 'INSERT', 'UPDATE', 'REFERENCES'):
            assert not conn.scalar(text('SELECT has_any_column_privilege(:role, :tabela, :priv)'), {'role': role, 'tabela': 'public.' + tabela, 'priv': priv})
        for priv in ('DELETE', 'TRUNCATE', 'TRIGGER'):
            assert not conn.scalar(text('SELECT has_table_privilege(:role, :tabela, :priv)'), {'role': role, 'tabela': 'public.' + tabela, 'priv': priv})
    engine = engine_login(pg, 'rb_api_probe')
    try:
        for sql in (f'SELECT * FROM public.{tabela}', f'DELETE FROM public.{tabela}',
                    f'TRUNCATE public.{tabela}'):
            with pytest.raises(ProgrammingError) as erro:
                with engine.begin() as conn:
                    conn.execute(text(f'SET LOCAL ROLE {role}'))
                    conn.execute(text(sql))
            assert erro.value.orig.pgcode == '42501'
    finally:
        engine.dispose()


def test_runtime_estoque_privilegios_minimos(pg, runtime_pg):
    from sqlalchemy.exc import ProgrammingError
    with pg.connect() as conn:
        for tabela in ('produtos_estoque', 'movimentos_estoque'):
            assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid=cast(:nome as regclass)"), {'nome': 'public.' + tabela})
        for coluna in ('id', 'filial_id'):
            assert not conn.scalar(text("SELECT has_column_privilege('relaxabarber_runtime', 'public.produtos_estoque', :coluna, 'UPDATE')"), {'coluna': coluna})
        assert conn.scalar(text("SELECT has_column_privilege('relaxabarber_runtime', 'public.produtos_estoque', 'saldo', 'UPDATE')"))
    for sql in ('UPDATE public.produtos_estoque SET filial_id=filial_id',
                'UPDATE public.produtos_estoque SET id=id',
                "UPDATE public.movimentos_estoque SET motivo='alterado'",
                'DELETE FROM public.produtos_estoque', 'TRUNCATE public.movimentos_estoque'):
        with pytest.raises(ProgrammingError) as erro:
            with runtime_pg.begin() as conn:
                conn.execute(text(sql))
        assert erro.value.orig.pgcode == '42501'

@pytest.mark.parametrize('alteracao', [
    'ALTER ROLE relaxabarber_runtime BYPASSRLS',
    'ALTER ROLE relaxabarber_runtime RENAME TO runtime_indisponivel_teste',
])
def test_migracao_recusa_runtime_inseguro_sem_alterar_dados(pg, caso, alteracao):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy.exc import DBAPIError
    from test_modelagem_filiais import scripts
    with pg.connect() as conn:
        antes = conn.scalar(text('SELECT count(*) FROM public.comandas'))
    with pytest.raises(DBAPIError) as erro:
        with pg.begin() as conn:
            conn.execute(text(alteracao))
            with Operations.context(MigrationContext.configure(conn)):
                scripts().get_revision('e70c15a9f321').module.upgrade()
    assert erro.value.orig.pgcode == 'P0001'
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM public.comandas')) == antes
        assert conn.scalar(text("SELECT NOT rolbypassrls AND NOT rolsuper FROM pg_roles WHERE rolname='relaxabarber_runtime'"))
