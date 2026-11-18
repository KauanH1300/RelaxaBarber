from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_financeiro_servicos import caso
from test_financeiro_persistencia import data, legado, financeiro


def test_excecao_servico_por_profissional_e_filial(runtime_pg, caso):
    from app.models import Servico, Usuario
    from app.api.routes.comissoes import ExcecaoDados, definir, listar
    with Session(runtime_pg, expire_on_commit=False) as db:
        admin=db.get(Usuario,caso['atores']['admin']); recepcao=db.get(Usuario,caso['atores']['recepcao'])
        servico=db.scalar(select(Servico.id)); profissional=caso['user']
        dados=ExcecaoDados(servico_id=servico,percentual=Decimal('35'))
        resultado=definir(profissional,dados,caso['filial'],db,admin)
        assert resultado.percentual==Decimal('35.00')
        atualizado=definir(profissional,ExcecaoDados(servico_id=servico,percentual=Decimal('0')),caso['filial'],db,admin)
        assert atualizado.id==resultado.id and atualizado.percentual==0
        assert len(listar(profissional,caso['filial'],db,admin))==1
        with pytest.raises(HTTPException) as exc: listar(profissional,caso['filial'],db,recepcao)
        assert exc.value.status_code==403
        with pytest.raises(HTTPException): listar(profissional,caso['outra_filial'],db,admin)


def test_produto_comissao_padrao_e_compatibilidade_de_edicao(runtime_pg, caso):
    from app.models import Usuario
    from app.api.routes.estoque import ProdutoDados,criar,atualizar
    with Session(runtime_pg, expire_on_commit=False) as db:
        admin=db.get(Usuario,caso['atores']['admin'])
        dados=dict(nome='Item fictício',unidade='un',venda=True,consumo=False,custo=Decimal('1'),preco_venda=Decimal('2'),estoque_minimo=Decimal('0'))
        produto=criar(ProdutoDados(**dados,comissao_padrao=Decimal('12.50')),caso['filial'],db,admin)
        assert produto.comissao_padrao==Decimal('12.50')
        produto=atualizar(produto.id,ProdutoDados(**dados),caso['filial'],db,admin)
        assert produto.comissao_padrao==Decimal('12.50')


def test_percentual_produto_nao_exposto_recepcao(runtime_pg, caso):
    import json
    from app.models import Usuario
    from app.api.routes.estoque import ProdutoDados, criar, listar
    with Session(runtime_pg, expire_on_commit=False) as db:
        admin=db.get(Usuario,caso['atores']['admin']); recepcao=db.get(Usuario,caso['atores']['recepcao'])
        criar(ProdutoDados(nome='Produto de teste',unidade='un',venda=True,consumo=False,custo=Decimal('1'),preco_venda=Decimal('2'),estoque_minimo=0,comissao_padrao=Decimal('25')),caso['filial'],db,admin)
        resposta=listar(caso['filial'],db,recepcao)
        assert resposta.status_code==200 and 'comissao_padrao' not in json.loads(resposta.body)[0]


def test_excecao_produto_exige_venda_e_filial(runtime_pg, caso):
    from app.models import Usuario
    from app.api.routes.estoque import ProdutoDados, criar
    from app.api.routes.comissoes import definir, ExcecaoDados
    with Session(runtime_pg,expire_on_commit=False) as db:
        admin=db.get(Usuario,caso['atores']['admin'])
        dados=dict(unidade='un',custo=Decimal('1'),estoque_minimo=Decimal('0'))
        vendavel=criar(ProdutoDados(nome='Produto fictício',venda=True,consumo=True,preco_venda=Decimal('2'),**dados),caso['filial'],db,admin)
        insumo=criar(ProdutoDados(nome='Insumo fictício',venda=False,consumo=True,**dados),caso['filial'],db,admin)
        resposta=definir(caso['user'],ExcecaoDados(produto_id=vendavel.id,percentual=Decimal('100')),caso['filial'],db,admin)
        assert resposta.produto_id==vendavel.id and resposta.percentual==100
        with pytest.raises(HTTPException) as exc: definir(caso['user'],ExcecaoDados(produto_id=insumo.id,percentual=Decimal('10')),caso['filial'],db,admin)
        assert exc.value.status_code==404


def test_acl_eventos_comissao(pg):
    with pg.connect() as c:
        for role in ('anon','authenticated','service_role'):
            for table in ('comissoes_item','eventos_comissao','excecoes_comissao'):
                assert not c.scalar(text("SELECT has_any_column_privilege(:role,:table,'SELECT')"),{'role':role,'table':'public.'+table})
            assert not c.scalar(text("SELECT has_sequence_privilege(:role,'public.eventos_comissao_ordem_seq','USAGE')"),{'role':role})
        assert not c.scalar(text("SELECT has_any_column_privilege('relaxabarber_runtime','public.eventos_comissao','UPDATE')"))
