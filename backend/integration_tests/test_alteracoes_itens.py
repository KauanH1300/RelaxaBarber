"""Ajustes e migração somente no PostgreSQL descartável validado pelo conftest."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import text, event
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session
from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso, ator, disputar, consultar, contagens
from test_financeiro_http import api, requisitar
from test_itens_comanda import aberta, incluir


@pytest.fixture
def itens(pg, aberta):
    s=aberta
    with pg.begin() as c:
        c.execute(text("UPDATE itens_comanda SET quantidade=3,preco_unitario=10,servico_id=:service WHERE comanda_id=:comanda"),s)
        c.execute(text('UPDATE comandas SET valor_total=30 WHERE id=:comanda'),s)
        item=c.scalar(text('SELECT id FROM itens_comanda WHERE comanda_id=:comanda'),s)
        novo=uuid4()
        c.execute(text("INSERT INTO servicos(id,nome,preco,tempo_estimado,comissao_padrao,ativo) VALUES(:id,'Novo ficticio',5,30,0,true)"),{'id':novo})
    return s|{'item':item,'novo':novo}


def dados(s,acao='quantidade',quantidade=2,versao=0):
    from app.schemas.itens_comanda import PreviaAlteracaoCreate
    return PreviaAlteracaoCreate(acao=acao,versao=versao,motivo='Ajuste ficticio conferido',
        **({'quantidade':quantidade} if acao!='remover' else {}),**({'servico_id':s['novo']} if acao=='substituir' else {}))


def preparar(db,s,d=None,perfil='recepcao'):
    from app.services.alteracoes_itens import previa
    from app.schemas.itens_comanda import AlteracaoItemCreate
    d=d or dados(s)
    p=previa(s['comanda'],s['item'],d,db,ator(db,s,perfil),s['filial'])
    return p,AlteracaoItemCreate(**d.model_dump(),conferencia=p.conferencia)


def aplicar(db,s,d,key=None,perfil='recepcao'):
    from app.services.alteracoes_itens import aplicar as executar
    return executar(s['comanda'],s['item'],d,key or uuid4(),db,ator(db,s,perfil),s['filial'])


def receber(db,s,valor):
    from app.services.financeiro import registrar_recebimentos
    return registrar_recebimentos(s['comanda'],pagamentos=[{'valor':Decimal(valor),'forma':'dinheiro','recebido_em':datetime.now(timezone.utc)-timedelta(minutes=1),'confirmado':True}],chave_idempotencia=uuid4(),db=db,usuario=ator(db,s),filial_id=s['filial'])


def estado(pg,s):
    with pg.connect() as c:
        return tuple(c.execute(text('SELECT quantidade,preco_unitario,ativo FROM itens_comanda WHERE id=:item'),s).one()),tuple(c.execute(text('SELECT status,versao_itens FROM comandas WHERE id=:comanda'),s).one()),c.scalar(text('SELECT count(*) FROM alteracoes_itens_comanda'))


@pytest.mark.parametrize('acao',['quantidade','substituir','remover'])
def test_ajuste_total_saldo_historico_e_replay(runtime_pg,pg,itens,acao):
    from app.services.alteracoes_itens import historico
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira
    s=itens;key=uuid4()
    with Session(runtime_pg) as db:
        p,d=preparar(db,s,dados(s,acao));assert estado(pg,s)[2]==0
        r=aplicar(db,s,d,key);assert r.anterior.preco_unitario==10 and r.versao==1 and not r.fechado
        assert r.total=={'quantidade':20,'substituir':10,'remover':0}[acao]
        assert r.posterior.preco_unitario==(5 if acao=='substituir' else 10)
        assert aplicar(db,s,d,key)==r
        assert consultar(db,s).total==r.total and consultar(db,s).saldo==r.total
        assert historico(s['comanda'],db,ator(db,s),s['filial'])==[r]
        with pytest.raises(ConflitoIdempotenciaFinanceira):aplicar(db,s,d.model_copy(update={'motivo':'Outro motivo'}),key)
    assert estado(pg,s)[2]==1 and contagens(pg)==(0,0,0)


def test_opcao_b_confirmacao_e_cancelamento_sem_escrita(runtime_pg,pg,itens):
    from app.services.financeiro_errors import ConfirmacaoAjusteNecessaria
    s=itens
    with Session(runtime_pg) as db:
        receber(db,s,'10');antes=estado(pg,s)
        p,d=preparar(db,s,dados(s,quantidade=1));assert p.exige_fechamento and p.saldo==0
        db.rollback()  # Usuário cancela: prévia não tem escrita.
        assert estado(pg,s)==antes
        with pytest.raises(ConfirmacaoAjusteNecessaria):aplicar(db,s,d)
        assert estado(pg,s)==antes and contagens(pg)==(1,0,0)
        key=uuid4();r=aplicar(db,s,d.model_copy(update={'confirmar_fechamento':True}),key)
        assert r.fechado and r.total==r.recebido_liquido==10
        assert aplicar(db,s,d.model_copy(update={'confirmar_fechamento':True}),key)==r
        assert consultar(db,s).situacao=='fechado'
    assert estado(pg,s)[1]==('fechada',1) and contagens(pg)==(1,0,1)


def test_remocao_com_outro_item_quita_sem_pagamento_ficticio(runtime_pg,pg,itens):
    s=itens
    with pg.begin() as c:
        c.execute(text("INSERT INTO itens_comanda(id,comanda_id,tipo,servico_id,descricao,quantidade,preco_unitario) VALUES(:id,:comanda,'servico',:service,'Outro',1,10)"),s|{'id':uuid4()})
    with Session(runtime_pg) as db:
        receber(db,s,'10');p,d=preparar(db,s,dados(s,'remover'));assert p.exige_fechamento
        r=aplicar(db,s,d.model_copy(update={'confirmar_fechamento':True}));assert r.fechado and not r.posterior.ativo
    assert contagens(pg)==(1,0,1)


def test_total_zero_sem_recebimento_permanece_aberto(runtime_pg,pg,itens):
    with Session(runtime_pg) as db:
        p,d=preparar(db,itens,dados(itens,'remover'));assert not p.exige_fechamento
        r=aplicar(db,itens,d);assert r.total==r.saldo==0 and not r.fechado
        assert consultar(db,itens).situacao=='aberto'
    assert contagens(pg)==(0,0,0)


def test_reducao_abaixo_do_recebido_bloqueada(runtime_pg,pg,itens):
    from app.services.financeiro_errors import SaldoInsuficiente
    with Session(runtime_pg) as db:
        receber(db,itens,'20');antes=estado(pg,itens)
        for d in [dados(itens,quantidade=1),dados(itens,'remover')]:
            with pytest.raises(SaldoInsuficiente):preparar(db,itens,d)
            db.rollback()
        assert estado(pg,itens)==antes
    assert contagens(pg)==(1,0,0)


@pytest.mark.parametrize('mudanca',['catalogo','pagamento','versao','fechamento'])
def test_previa_desatualizada_nao_aplica(runtime_pg,pg,itens,mudanca):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=itens
    with Session(runtime_pg) as db:
        _,d=preparar(db,s,dados(s,'substituir' if mudanca=='catalogo' else 'quantidade'));db.rollback()
        if mudanca=='catalogo':
            with pg.begin() as c:c.execute(text('UPDATE servicos SET preco=7 WHERE id=:novo'),s)
        elif mudanca=='versao':
            _,other=preparar(db,s,dados(s,quantidade=4));aplicar(db,s,other)
        else:receber(db,s,'30' if mudanca=='fechamento' else '5')
        antes=estado(pg,s)
        with pytest.raises(EstadoFinanceiroIncompativel):aplicar(db,s,d)
        assert estado(pg,s)==antes


@pytest.mark.parametrize('perfil',['admin','recepcao','barbeiro','barbeiro_chefe','outro'])
def test_permissoes_http(api,pg,itens,perfil):
    s=itens;payload=dados(s).model_dump(mode='json')
    r=requisitar(api,s,'itens/'+str(s['item'])+'/previa',perfil=perfil,body=payload)
    assert r[0]==(200 if perfil in ['admin','recepcao'] else 403 if perfil=='barbeiro' else 404)
    if r[0]==200:
        body=payload|{'conferencia':r[1]['conferencia'],'confirmar_fechamento':False}
        result=requisitar(api,s,'itens/'+str(s['item'])+'/alteracoes',perfil=perfil,body=body,key=uuid4());assert result[0]==200
    else:assert estado(pg,s)[2]==0


@pytest.mark.parametrize('mudanca',[{'quantidade':0},{'quantidade':1.5},{'quantidade':True},{'preco_unitario':'1'},{'motivo':' '},{'acao':'produto'},{'servico_id':str(uuid4())}])
def test_payload_invalido_sem_escrita(api,pg,itens,mudanca):
    p=dados(itens).model_dump(mode='json')|mudanca
    assert requisitar(api,itens,'itens/'+str(itens['item'])+'/previa',body=p)[0]==422
    assert estado(pg,itens)[2]==0


def test_inclusao_recupera_resposta_original_apos_editar_e_remover(runtime_pg,pg,itens):
    s=itens;key=uuid4()
    with Session(runtime_pg) as db:
        original=incluir(db,s,chave_idempotencia=key,quantidade=1)
        s=s|{'item':original.item.id}
        _,d=preparar(db,s,dados(s,quantidade=2,versao=1));aplicar(db,s,d)
        assert incluir(db,s,chave_idempotencia=key,quantidade=1)==original
        _,d=preparar(db,s,dados(s,'remover',versao=2));aplicar(db,s,d)
        assert incluir(db,s,chave_idempotencia=key,quantidade=1)==original
        assert not estado(pg,s)[0][2]


@pytest.mark.parametrize('modo',['replay','versao','pagamento_primeiro','ajuste_primeiro','quitacao_primeiro'])
def test_concorrencia_serializada(runtime_pg,pg,itens,modo):
    from app.services.financeiro_errors import VersaoItensDesatualizada, SaldoInsuficiente, EstadoFinanceiroIncompativel
    s=itens;key=uuid4()
    with Session(runtime_pg) as db:_,d=preparar(db,s)
    edit=lambda db:aplicar(db,s,d,key)
    pay=lambda db:receber(db,s,'30' if modo=='quitacao_primeiro' else '25')
    if modo in ['replay','versao']:
        one,two=disputar(runtime_pg,edit,edit if modo=='replay' else lambda db:aplicar(db,s,d,uuid4()))
        if modo=='replay':assert one==two
        else:assert isinstance(two,VersaoItensDesatualizada)
        assert estado(pg,s)[2]==1
    else:
        one,two=disputar(runtime_pg,pay if modo!='ajuste_primeiro' else edit,edit if modo!='ajuste_primeiro' else pay)
        assert isinstance(two,EstadoFinanceiroIncompativel if modo=='quitacao_primeiro' else SaldoInsuficiente)
        assert estado(pg,s)[2]==(1 if modo=='ajuste_primeiro' else 0)


def test_falha_na_auditoria_reverte_ajuste_e_fechamento(runtime_pg,pg,itens):
    with Session(runtime_pg) as db:
        receber(db,itens,'10');_,d=preparar(db,itens,dados(itens,quantidade=1));d=d.model_copy(update={'confirmar_fechamento':True});db.rollback()
    before=estado(pg,itens)
    def falhar(c,cursor,sql,params,context,many):
        if sql.startswith('INSERT INTO alteracoes_itens_comanda'):raise RuntimeError('Falha ficticia')
    event.listen(runtime_pg,'before_cursor_execute',falhar)
    try:
        with Session(runtime_pg) as db,pytest.raises(RuntimeError):aplicar(db,itens,d)
    finally:event.remove(runtime_pg,'before_cursor_execute',falhar)
    assert estado(pg,itens)==before and contagens(pg)==(1,0,0)


@pytest.mark.parametrize('commit_real',[False,True])
def test_timeout_e_recuperacao_original(pg,itens,commit_real):
    from app.services.persistencia import ConfirmacaoIndeterminada
    with Session(pg) as db:_,d=preparar(db,itens)
    class Incerta(Session):
        def commit(self):
            if commit_real:super().commit()
            raise OperationalError(None,{},SimpleNamespace(pgcode='08006'),connection_invalidated=True)
    key=uuid4()
    with Incerta(pg) as db,pytest.raises(ConfirmacaoIndeterminada):aplicar(db,itens,d,key)
    with Session(pg) as db:
        r=aplicar(db,itens,d,key);assert aplicar(db,itens,d,key)==r
    assert estado(pg,itens)[2]==1


def test_auditoria_e_respostas_imutaveis(runtime_pg,pg,itens):
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens);aplicar(db,itens,d)
        incluir(db,itens,quantidade=1)
    for table in ['alteracoes_itens_comanda','respostas_inclusoes_comanda']:
        for sql in [f'DELETE FROM {table}',f'UPDATE {table} SET '+('motivo=motivo' if table.startswith('alteracoes') else 'resposta=resposta')]:
            with pytest.raises(DBAPIError),pg.begin() as c:c.execute(text(sql))
        with pg.connect() as c:
            assert c.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:table AS regclass)'),{'table':table})
            for role in ['anon','authenticated','service_role']:
                assert not c.scalar(text('SELECT has_any_column_privilege(:role,:table,\'SELECT,INSERT,UPDATE,REFERENCES\')'),{'role':role,'table':table})


def test_migracao_congela_inclusao_preexistente(pg,itens):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from test_modelagem_filiais import scripts
    s=itens;key=uuid4();inc=uuid4()
    with pg.begin() as c:
        c.execute(text("INSERT INTO inclusoes_servicos_comanda(id,comanda_id,filial_id,item_id,registrado_por,chave_idempotencia,fingerprint,total_resultante) VALUES(:inc,:comanda,:filial,:item,:user,:key,:fp,30)"),s|{'inc':inc,'key':key,'fp':'a'*64})
        before=c.scalar(text('SELECT to_jsonb(a) FROM inclusoes_servicos_comanda a WHERE id=:id'),{'id':inc})
        # Estado imediatamente anterior à nova revisão, somente nesta base descartável.
        c.execute(text('DROP TABLE alteracoes_itens_comanda'))
        c.execute(text('DROP TABLE respostas_inclusoes_comanda'))
        c.execute(text('DROP FUNCTION public.itens_carimbar_alteracao()'))
        c.execute(text('ALTER TABLE itens_comanda DROP COLUMN ativo'))
        c.execute(text('ALTER TABLE comandas DROP COLUMN versao_itens'))
        with Operations.context(MigrationContext.configure(c)):scripts().get_revision('c61e9a4b207d').module.upgrade()
        assert c.scalar(text('SELECT to_jsonb(a) FROM inclusoes_servicos_comanda a WHERE id=:id'),{'id':inc})==before
        frozen=c.scalar(text('SELECT resposta FROM respostas_inclusoes_comanda WHERE inclusao_id=:id'),{'id':inc})
        assert frozen['item']['quantidade']==3 and frozen['item']['preco_unitario']=='10.00' and frozen['total']=='30.00'
        assert c.scalar(text('SELECT ativo FROM itens_comanda WHERE id=:item'),s) is True
        assert c.scalar(text('SELECT versao_itens FROM comandas WHERE id=:comanda'),s)==0


def test_removidos_excluidos_do_detalhe_painel_e_financeiro(runtime_pg,pg,itens):
    from app.services.comandas import buscar_detalhe, consultar_painel
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens,dados(itens,'remover'));aplicar(db,itens,d)
        user=ator(db,itens)
        detalhe=buscar_detalhe(db,user,itens['comanda'],itens['filial'])
        assert detalhe.itens==[] and detalhe.total==0 and detalhe.versao_itens==1
        painel=consultar_painel(db,user,itens['filial'])
        assert painel.itens[0].itens==[] and painel.itens[0].total==0
        assert painel.indicadores.valor_abertas==0
        assert consultar(db,itens).total==0
    with pg.connect() as c:assert c.scalar(text('SELECT count(*) FROM itens_comanda WHERE id=:item'),itens)==1


def test_quantidade_preserva_historico_com_catalogo_inativo(runtime_pg,pg,itens):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with pg.begin() as c:c.execute(text('UPDATE servicos SET ativo=false,preco=99 WHERE id IN (:service,:novo)'),itens)
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens);r=aplicar(db,itens,d)
        assert r.posterior.preco_unitario==10 and r.total==20
        with pytest.raises(EntradaFinanceiraInvalida):preparar(db,itens,dados(itens,'substituir',versao=1))


def test_revogacao_bloqueia_replay(runtime_pg,pg,itens):
    from app.services.financeiro_errors import ComandaFinanceiraNaoEncontrada
    key=uuid4()
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens);aplicar(db,itens,d,key)
    with pg.begin() as c:c.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:u'),{'u':itens['atores']['recepcao']})
    with Session(runtime_pg) as db,pytest.raises(ComandaFinanceiraNaoEncontrada):aplicar(db,itens,d,key)
    assert estado(pg,itens)[2]==1


def test_datas_auditoria_e_fechamento_sao_carimbadas_pelo_banco(runtime_pg,pg,itens):
    with Session(runtime_pg) as db:
        receber(db,itens,'10');_,d=preparar(db,itens,dados(itens,quantidade=1))
        r=aplicar(db,itens,d.model_copy(update={'confirmar_fechamento':True}))
    with pg.connect() as c:
        assert c.scalar(text('SELECT registrado_em FROM alteracoes_itens_comanda'))==r.registrado_em
        assert c.scalar(text('SELECT data_fechamento FROM comandas WHERE id=:comanda'),itens)==c.scalar(text('SELECT registrado_em FROM fechamentos_financeiros_comanda'))


def test_total_central_rejeita_nao_finito_e_ignora_removido(runtime_pg,pg,itens):
    from app.models import Comanda
    from app.services.financeiro import _total
    from app.services.financeiro_errors import DadosFinanceirosInconsistentes
    with pg.begin() as c:c.execute(text("UPDATE itens_comanda SET preco_unitario='NaN' WHERE id=:item"),itens)
    with Session(runtime_pg) as db,pytest.raises(DadosFinanceirosInconsistentes):_total(db,db.get(Comanda,itens['comanda']))
    with pg.begin() as c:c.execute(text('UPDATE itens_comanda SET ativo=false WHERE id=:item'),itens)
    with Session(runtime_pg) as db:assert _total(db,db.get(Comanda,itens['comanda']))==0
