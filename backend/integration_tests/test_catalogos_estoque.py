from uuid import uuid4
import pytest
from test_financeiro_servicos import caso
from test_financeiro_http import api
from test_financeiro_persistencia import data, legado, financeiro
from test_seguranca_horarios import chamar

def test_catalogos_e_produtos_por_filial(api, runtime_pg, pg, caso):
    from app.core.security import criar_token
    admin = criar_token(caso['atores']['admin'])
    recepcao = criar_token(caso['atores']['recepcao'])
    barbeiro = criar_token(caso['atores']['barbeiro'])
    filial = caso['filial']
    base = f'/estoque/catalogos/categorias?filial_id={filial}'
    assert chamar(api, base, method='POST', dados={'nome':'  Cabelo  '}, token=admin)[0] == 201
    categoria = chamar(api, base, token=recepcao)[1][0]
    assert categoria['nome'] == 'Cabelo'
    assert chamar(api, base, method='POST', dados={'nome':'cAbElO'}, token=admin)[0] == 409
    assert chamar(api, base, method='POST', dados={'nome':'Outra'}, token=recepcao)[0] == 403
    assert chamar(api, base, token=barbeiro)[0] == 403
    marca_url = f'/estoque/catalogos/marcas?filial_id={filial}'
    status, marca = chamar(api, marca_url, method='POST', dados={'nome':'Marca QA'}, token=admin)
    assert status == 201
    produtos = f'/estoque/produtos?filial_id={filial}'
    body = {'nome':'Item QA','unidade':'un','venda':True,'consumo':True,'custo':'2','preco_venda':'5','estoque_minimo':'1','comissao_padrao':'12'}
    status, sem = chamar(api, produtos, method='POST', dados=body, token=admin)
    assert status == 201 and sem['categoria_id'] is None and sem['marca_id'] is None
    status, item = chamar(api, produtos, method='POST', dados=body | {'categoria_id':categoria['id'],'marca_id':marca['id']}, token=admin)
    assert status == 201 and item['categoria_id'] == categoria['id'] and item['marca_id'] == marca['id']
    url = f"/estoque/produtos/{item['id']}?filial_id={filial}"
    status, item = chamar(api, url, method='PUT', dados=body, token=admin)
    assert status == 200 and item['categoria_id'] == categoria['id'] and item['marca_id'] == marca['id']
    assert chamar(api, url, method='PUT', dados=body | {'categoria_id':str(uuid4())}, token=admin)[0] == 404
    from sqlalchemy import text
    outra_categoria = uuid4()
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO categorias_estoque(id,filial_id,nome) VALUES (:id,:filial,'Cabelo')"), {'id':outra_categoria, 'filial':caso['outra_filial']})
    assert chamar(api, url, method='PUT', dados=body | {'categoria_id':str(outra_categoria)}, token=admin)[0] == 404
    assert all(c['id'] != str(outra_categoria) for c in chamar(api, base, token=admin)[1])
    status, item = chamar(api, url, method='PUT', dados=body | {'categoria_id':None,'marca_id':None}, token=admin)
    assert status == 200 and item['categoria_id'] is None and item['marca_id'] is None

@pytest.mark.parametrize('nome', ['', '   ', 'linha\nquebrada', 'x' * 101])
def test_nome_invalido(nome):
    from app.api.routes.estoque import NomeCatalogo
    from pydantic import ValidationError
    with pytest.raises(ValidationError): NomeCatalogo(nome=nome)

def test_cadastro_concorrente_e_acl(runtime_pg, pg, caso):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from app.models import Usuario
    from app.api.routes.estoque import criar_catalogo, NomeCatalogo
    barrier = Barrier(2)
    def executar(_):
        with Session(runtime_pg, expire_on_commit=False) as db:
            ator = db.get(Usuario, caso['atores']['admin'])
            barrier.wait()
            try:
                criar_catalogo('marcas', NomeCatalogo(nome='Mesma marca'), caso['filial'], db, ator)
                return 201
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(executar, range(2))) == [201, 409]
    with pg.connect() as db:
        for tabela in ('categorias_estoque', 'marcas_estoque'):
            assert db.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=cast(:t as regclass)'), {'t':'public.'+tabela})
            for papel in ('anon', 'authenticated', 'service_role'):
                assert not db.scalar(text('SELECT has_table_privilege(:p, :t, :v)'), {'p':papel, 't':'public.'+tabela, 'v':'SELECT'})

def test_migracao_preserva_produto_e_historico(pg, caso):
    from sqlalchemy import text
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from test_modelagem_filiais import scripts
    ident, movimento = uuid4(), uuid4()
    with pg.begin() as db:
        db.execute(text("INSERT INTO produtos_estoque(id,filial_id,nome,unidade,venda,consumo,custo,preco_venda,estoque_minimo,saldo,comissao_padrao) VALUES (:id,:filial,'Item legado','un',true,true,2,5,1,3,12)"), {'id':ident,'filial':caso['filial']})
        db.execute(text("INSERT INTO movimentos_estoque(id,produto_id,filial_id,tipo,quantidade,saldo_apos,motivo,registrado_por,chave_idempotencia) VALUES (:id,:produto,:filial,'entrada',3,3,'Teste',:ator,:chave)"), {'id':movimento,'produto':ident,'filial':caso['filial'],'ator':caso['atores']['admin'],'chave':uuid4()})
        db.execute(text('ALTER TABLE public.produtos_estoque DROP COLUMN categoria_id, DROP COLUMN marca_id'))
        db.execute(text('DROP TABLE public.categorias_estoque, public.marcas_estoque'))
        db.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        with Operations.context(MigrationContext.configure(db)):
            scripts().get_revision('a38f72b96c14').module.upgrade()
        item = db.execute(text('SELECT saldo,comissao_padrao,categoria_id,marca_id FROM produtos_estoque WHERE id=:id'), {'id':ident}).one()
        assert tuple(item) == (3,12,None,None)
        assert db.scalar(text('SELECT count(*) FROM movimentos_estoque WHERE id=:id'), {'id':movimento}) == 1
