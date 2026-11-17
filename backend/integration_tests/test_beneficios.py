"""Benefícios reais somente no PostgreSQL descartável; sem acesso ao Supabase."""
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace
import pytest
from sqlalchemy import text, event
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session
from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso, ator, consultar, contagens, disputar
from test_itens_comanda import aberta, incluir
from test_alteracoes_itens import itens, receber, dados as ajuste, preparar as preparar_item, aplicar as aplicar_item
from test_financeiro_http import api, requisitar


def dados(s, tipo='valor', valor='5', acao='item', versao=0):
    from app.schemas.beneficios import BeneficioPreviaCreate
    return BeneficioPreviaCreate(acao=acao,versao=versao,motivo='Benefício fictício conferido',
        desconto_tipo=tipo,desconto_valor=valor,**({'item_id':s['item']} if acao=='item' else {}))


def preparar(db,s,d=None,perfil='recepcao'):
    from app.services.beneficios import previa
    from app.schemas.beneficios import BeneficioCreate
    d=d or dados(s)
    p=previa(s['comanda'],d,db,ator(db,s,perfil),s['filial'])
    return p,BeneficioCreate(**d.model_dump(),conferencia=p.conferencia)


def aplicar(db,s,d,key=None,perfil='recepcao'):
    from app.services.beneficios import aplicar as run
    return run(s['comanda'],d,key or uuid4(),db,ator(db,s,perfil),s['filial'])


def auditorias(pg):
    with pg.connect() as c:return c.scalar(text('SELECT count(*) FROM beneficios_comanda'))


@pytest.mark.parametrize('tipo,valor,total',[('valor','5','25'),('percentual','25','22.50'),('cortesia','0','0')])
def test_individual_historico_auditoria_e_replay(runtime_pg,pg,itens,tipo,valor,total):
    from app.services.beneficios import historico
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira
    s=itens;key=uuid4()
    with Session(runtime_pg) as db:
        p,d=preparar(db,s,dados(s,tipo,valor));assert auditorias(pg)==0
        r=aplicar(db,s,d,key)
        assert r.posterior.total==Decimal(total) and not r.fechado
        assert r.anterior.itens[0].preco_unitario==r.posterior.itens[0].preco_unitario==10
        assert consultar(db,s).total==r.posterior.total
        assert aplicar(db,s,d,key)==r
        assert historico(s['comanda'],db,ator(db,s),s['filial'])==[r]
        with pytest.raises(ConflitoIdempotenciaFinanceira):aplicar(db,s,d.model_copy(update={'motivo':'Outro'}),key)
    assert auditorias(pg)==1 and contagens(pg)==(0,0,0)


@pytest.mark.parametrize('tipo,valor,total',[('valor','5','19'),('percentual','25','18')])
def test_ordem_individual_antes_do_geral_e_projecao(runtime_pg,pg,itens,tipo,valor,total):
    from app.services.comandas import buscar_detalhe, consultar_painel
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens,dados(itens,'percentual','20'));aplicar(db,itens,d)
        _,d=preparar(db,itens,dados(itens,tipo,valor,'comanda',1));r=aplicar(db,itens,d)
        assert r.posterior.total==Decimal(total) and r.posterior.subtotal==24
        detail=buscar_detalhe(db,ator(db,itens),itens['comanda'],itens['filial'])
        assert detail.total==consultar(db,itens).total==Decimal(total)
        painel=consultar_painel(db,ator(db,itens),itens['filial'])
        assert painel.itens[0].total==Decimal(total) and painel.indicadores.valor_abertas==Decimal(total)
    assert auditorias(pg)==2


def test_desconto_geral_recalcula_apos_incluir_editar_remover(runtime_pg,pg,itens):
    s=itens
    with Session(runtime_pg) as db:
        _,d=preparar(db,s,dados(s,'percentual','10','comanda'));aplicar(db,s,d)
        r=incluir(db,s,quantidade=1);assert r.total==54  # catálogo 30 + histórico 30, menos 10%
        _,d=preparar_item(db,s,ajuste(s,quantidade=2,versao=2));a=aplicar_item(db,s,d);assert a.total==45
        _,d=preparar_item(db,s,ajuste(s,'remover',versao=3));a=aplicar_item(db,s,d);assert a.total==27
        assert consultar(db,s).total==27


@pytest.mark.parametrize('acao',['item','comanda'])
def test_reducao_quantidade_com_desconto_fixo_invalido_bloqueada(runtime_pg,pg,itens,acao):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens,dados(itens,'valor','25',acao));aplicar(db,itens,d)
        with pytest.raises(EntradaFinanceiraInvalida):preparar_item(db,itens,ajuste(itens,quantidade=2,versao=1))
        db.rollback()
        assert consultar(db,itens).total==5


def test_substituicao_nao_transfere_cortesia_e_replay_congela_historico(runtime_pg,pg,itens):
    s=itens;key=uuid4()
    with Session(runtime_pg) as db:
        _,d=preparar(db,s,dados(s,'cortesia','0'));r=aplicar(db,s,d,key)
        _,ed=preparar_item(db,s,ajuste(s,'substituir',versao=1));a=aplicar_item(db,s,ed)
        assert a.total==10 and a.posterior.desconto_tipo=='nenhum' and a.anterior.desconto_tipo=='cortesia'
        assert aplicar(db,s,d,key)==r


def test_opcao_b_revalida_confirma_e_fecha_atomicamente(runtime_pg,pg,itens):
    from app.services.financeiro_errors import ConfirmacaoAjusteNecessaria, EstadoFinanceiroIncompativel
    with Session(runtime_pg) as db:
        receber(db,itens,'10')
        p,d=preparar(db,itens,dados(itens,'valor','20'));assert p.exige_fechamento
        db.rollback();assert auditorias(pg)==0 and contagens(pg)==(1,0,0)
        with pytest.raises(ConfirmacaoAjusteNecessaria):aplicar(db,itens,d)
        assert auditorias(pg)==0
        key=uuid4();d=d.model_copy(update={'confirmar_fechamento':True});r=aplicar(db,itens,d,key)
        assert r.fechado and consultar(db,itens).situacao=='fechado'
        assert aplicar(db,itens,d,key)==r
        with pytest.raises(EstadoFinanceiroIncompativel):preparar(db,itens,dados(itens,versao=1))
    assert auditorias(pg)==1 and contagens(pg)==(1,0,1)


@pytest.mark.parametrize('tipo,valor,acao',[('cortesia','0','item'),('percentual','100','comanda')])
def test_gratuidade_explicita_sem_pagamento_e_sem_autoencerrar(runtime_pg,pg,itens,tipo,valor,acao):
    from app.services.financeiro_errors import ConfirmacaoAjusteNecessaria
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens,dados(itens,tipo,valor,acao));r=aplicar(db,itens,d)
        assert not r.fechado and consultar(db,itens).situacao=='aberto' and contagens(pg)==(0,0,0)
        p,d=preparar(db,itens,dados(itens,'nenhum','0','encerramento_gratuito',1));assert p.exige_gratuidade
        db.rollback()
        with pytest.raises(ConfirmacaoAjusteNecessaria):aplicar(db,itens,d)
        key=uuid4();d=d.model_copy(update={'confirmar_gratuidade':True});r=aplicar(db,itens,d,key)
        assert r.fechado and r.posterior.total==0 and r.recebido_liquido==0
        assert aplicar(db,itens,d,key)==r and consultar(db,itens).situacao=='fechado'
    assert auditorias(pg)==2 and contagens(pg)==(0,0,1)


def test_vazia_nao_encerra_e_total_positivo_nao_e_gratuito(runtime_pg,pg,itens):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with Session(runtime_pg) as db:
        with pytest.raises(EstadoFinanceiroIncompativel):preparar(db,itens,dados(itens,'nenhum','0','encerramento_gratuito'))
        db.rollback()
        _,d=preparar_item(db,itens,ajuste(itens,'remover'));aplicar_item(db,itens,d)
        with pytest.raises(EstadoFinanceiroIncompativel):preparar(db,itens,dados(itens,'nenhum','0','encerramento_gratuito',1))
        db.rollback();assert consultar(db,itens).situacao=='aberto'
    assert auditorias(pg)==0 and contagens(pg)==(0,0,0)


@pytest.mark.parametrize('tipo,valor,acao',[('valor','31','item'),('valor','31','comanda')])
def test_desconto_superior_a_base(runtime_pg,pg,itens,tipo,valor,acao):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with Session(runtime_pg) as db,pytest.raises(EntradaFinanceiraInvalida):preparar(db,itens,dados(itens,tipo,valor,acao))
    assert auditorias(pg)==0


def test_abaixo_recebido_e_previa_desatualizada_por_pagamento(runtime_pg,pg,itens):
    from app.services.financeiro_errors import SaldoInsuficiente, VersaoItensDesatualizada
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens);db.rollback();receber(db,itens,'10')
        with pytest.raises(VersaoItensDesatualizada):aplicar(db,itens,d)
        with pytest.raises(SaldoInsuficiente):preparar(db,itens,dados(itens,'valor','25'))
    assert auditorias(pg)==0 and contagens(pg)==(1,0,0)


@pytest.mark.parametrize('modo',['replay','versao','pagamento','quitacao','gratuidade','beneficio_primeiro','edicao_primeiro','beneficio_antes_edicao'])
def test_concorrencia_real(runtime_pg,pg,itens,modo):
    from app.services.financeiro_errors import VersaoItensDesatualizada, EstadoFinanceiroIncompativel, SaldoInsuficiente
    s=itens;key=uuid4()
    with Session(runtime_pg) as db:
        if modo=='gratuidade':
            _,d=preparar(db,s,dados(s,'cortesia','0'));aplicar(db,s,d)
            _,d=preparar(db,s,dados(s,'nenhum','0','encerramento_gratuito',1));d=d.model_copy(update={'confirmar_gratuidade':True})
        else:
            _,d=preparar(db,s)
            if modo in ['edicao_primeiro','beneficio_antes_edicao']:_,ed=preparar_item(db,s,ajuste(s,quantidade=2))
    if modo in ['replay','gratuidade']:
        a,b=disputar(runtime_pg,lambda db:aplicar(db,s,d,key),lambda db:aplicar(db,s,d,key));assert a==b
    elif modo=='versao':
        a,b=disputar(runtime_pg,lambda db:aplicar(db,s,d),lambda db:aplicar(db,s,d));assert isinstance(b,VersaoItensDesatualizada)
    elif modo=='beneficio_primeiro':
        a,b=disputar(runtime_pg,lambda db:aplicar(db,s,d),lambda db:receber(db,s,'30'));assert isinstance(b,SaldoInsuficiente)
    elif modo=='edicao_primeiro':
        a,b=disputar(runtime_pg,lambda db:aplicar_item(db,s,ed),lambda db:aplicar(db,s,d));assert isinstance(b,VersaoItensDesatualizada)
    elif modo=='beneficio_antes_edicao':
        a,b=disputar(runtime_pg,lambda db:aplicar(db,s,d),lambda db:aplicar_item(db,s,ed));assert isinstance(b,VersaoItensDesatualizada)
    else:
        a,b=disputar(runtime_pg,lambda db:receber(db,s,'30' if modo=='quitacao' else '5'),lambda db:aplicar(db,s,d))
        assert isinstance(b,EstadoFinanceiroIncompativel)
    assert auditorias(pg)==(2 if modo=='gratuidade' else 1 if modo in ['replay','versao','beneficio_primeiro','beneficio_antes_edicao'] else 0)
    assert contagens(pg)==((0,0,1) if modo=='gratuidade' else (1,0,1) if modo=='quitacao' else (1,0,0) if modo=='pagamento' else (0,0,0))


@pytest.mark.parametrize('perfil',['admin','recepcao','barbeiro','barbeiro_chefe','outro'])
def test_permissoes_http(api,pg,itens,perfil):
    p=dados(itens).model_dump(mode='json');r=requisitar(api,itens,'beneficios/previa',perfil=perfil,body=p)
    assert r[0]==(200 if perfil in ['admin','recepcao'] else 403 if perfil=='barbeiro' else 404)
    if r[0]==200:
        body=p|{'conferencia':r[1]['conferencia']}
        assert requisitar(api,itens,'beneficios',perfil=perfil,body=body,key=uuid4())[0]==200
    else:
        assert requisitar(api,itens,'beneficios',perfil=perfil,body=p|{'conferencia':'0'*64},key=uuid4())[0]==r[0]
        assert auditorias(pg)==0


@pytest.mark.parametrize('mudanca',[{'desconto_valor':'-1'},{'desconto_valor':'100.01','desconto_tipo':'percentual'},
    {'desconto_valor':'NaN'},{'desconto_valor':'1.001'},{'motivo':' '},{'preco_unitario':'0'},
    {'desconto_tipo':'cortesia','desconto_valor':'1'},{'acao':'comanda','desconto_tipo':'cortesia','item_id':None,'desconto_valor':'0'},
    {'versao':True},{'desconto_valor':True}])
def test_payload_invalido_http_sem_escrita(api,pg,itens,mudanca):
    assert requisitar(api,itens,'beneficios/previa',body=dados(itens).model_dump(mode='json')|mudanca)[0]==422
    assert auditorias(pg)==0


def test_runtime_auditoria_imutavel_e_migration_padrao(runtime_pg,pg,itens):
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens);aplicar(db,itens,d)
    for sql in ['UPDATE beneficios_comanda SET motivo=motivo','DELETE FROM beneficios_comanda','TRUNCATE beneficios_comanda']:
        with pg.begin() as c,pytest.raises(DBAPIError):c.execute(text(sql))
    with pg.connect() as c:
        assert c.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='beneficios_comanda'::regclass"))
        for role in ['anon','authenticated','service_role']:
            assert not c.scalar(text("SELECT has_table_privilege(:r,'beneficios_comanda','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"),{'r':role})
        assert c.scalar(text("SELECT count(*) FROM pg_constraint WHERE conrelid IN ('comandas'::regclass,'itens_comanda'::regclass) AND conname IN ('ck_comanda_desconto','ck_item_desconto') AND convalidated"))==2


def test_falha_de_auditoria_reverte_beneficio_e_fechamento(runtime_pg,pg,itens):
    def falhar(conn,cursor,sql,params,context,many):
        if sql.lstrip().startswith('INSERT INTO beneficios_comanda'):raise RuntimeError('falha fictícia na auditoria')
    with Session(runtime_pg) as db:
        receber(db,itens,'10');_,d=preparar(db,itens,dados(itens,'valor','20'));d=d.model_copy(update={'confirmar_fechamento':True})
        event.listen(runtime_pg,'before_cursor_execute',falhar)
        try:
            with pytest.raises(RuntimeError,match='falha fictícia na auditoria'):aplicar(db,itens,d)
        finally:event.remove(runtime_pg,'before_cursor_execute',falhar)
        assert consultar(db,itens).total==30 and consultar(db,itens).situacao=='aberto'
    assert auditorias(pg)==0 and contagens(pg)==(1,0,0)


@pytest.mark.parametrize('base,individual,geral,total',[
    ('0.05','10','0','0.04'),('0.05','10','50','0.02'),('0.01','50','0','0'),
    ('19.99','12.50','7.75','16.13'),('0.00','100','100','0'),
])
def test_arredondamento_python_sql_dto_coincidem(runtime_pg,pg,itens,base,individual,geral,total):
    from app.services.totais_comanda import resumo_totais
    from app.services.comandas import buscar_detalhe
    with pg.begin() as c:
        c.execute(text('UPDATE itens_comanda SET quantidade=1,preco_unitario=:p WHERE id=:item'),itens|{'p':base})
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens,dados(itens,'percentual',individual));aplicar(db,itens,d)
        if geral!='0':
            _,d=preparar(db,itens,dados(itens,'percentual',geral,'comanda',1));aplicar(db,itens,d)
        detail=buscar_detalhe(db,ator(db,itens),itens['comanda'],itens['filial'])
        expected=Decimal(total)
        assert detail.total==consultar(db,itens).total==expected
        assert resumo_totais(detail.itens,detail.desconto_tipo,detail.desconto_valor)['total']==expected


@pytest.mark.parametrize('commit_real',[False,True])
def test_commit_incerto_recupera_resposta_original(pg,itens,commit_real):
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
    assert auditorias(pg)==1


def test_migracao_preserva_registros_preexistentes(pg,itens):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from test_modelagem_filiais import scripts
    with pg.begin() as c:
        c.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        # Reconstrução do predecessor exclusivamente nesta base efêmera.
        c.execute(text('DROP TABLE beneficios_comanda'))
        for table in ['comandas','itens_comanda']:
            c.execute(text(f'ALTER TABLE {table} DROP COLUMN desconto_tipo, DROP COLUMN desconto_valor'))
        old={t:c.scalar(text('SELECT jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text) FROM '+t+' t')) for t in ['comandas','itens_comanda','controles_financeiros_comanda','pagamentos_comanda','alteracoes_itens_comanda']}
        MigrationContext.configure(c).stamp(scripts(),'c61e9a4b207d')
        with Operations.context(MigrationContext.configure(c)):scripts().get_revision('ab72d90e613f').module.upgrade()
        MigrationContext.configure(c).stamp(scripts(),'ab72d90e613f')
        for t,before in old.items():
            expr="to_jsonb(t)-'desconto_tipo'-'desconto_valor'" if t in ['comandas','itens_comanda'] else 'to_jsonb(t)'
            assert c.scalar(text(f'SELECT jsonb_agg({expr} ORDER BY ({expr})::text) FROM {t} t'))==before
        assert c.scalar(text('SELECT version_num FROM alembic_version'))=='ab72d90e613f'
        assert c.scalar(text('SELECT count(*) FROM beneficios_comanda'))==0


def test_ajuste_pr56_com_geral_respeita_opcao_b(runtime_pg,pg,itens):
    from app.services.financeiro_errors import ConfirmacaoAjusteNecessaria
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens,dados(itens,'percentual','10','comanda'));aplicar(db,itens,d)
        receber(db,itens,'9');p,d=preparar_item(db,itens,ajuste(itens,quantidade=1,versao=1))
        assert p.total==9 and p.exige_fechamento
        with pytest.raises(ConfirmacaoAjusteNecessaria):aplicar_item(db,itens,d)
        r=aplicar_item(db,itens,d.model_copy(update={'confirmar_fechamento':True}))
        assert r.fechado and consultar(db,itens).situacao=='fechado'
    assert contagens(pg)==(1,0,1)


def test_recebimento_quita_total_descontado_automaticamente(runtime_pg,pg,itens):
    with Session(runtime_pg) as db:
        _,d=preparar(db,itens,dados(itens,'percentual','25'));aplicar(db,itens,d)
        _,d=preparar(db,itens,dados(itens,'percentual','20','comanda',1));aplicar(db,itens,d)
        assert consultar(db,itens).total==18
        receber(db,itens,'10');assert consultar(db,itens).saldo==8 and consultar(db,itens).situacao=='aberto'
        receber(db,itens,'8');assert consultar(db,itens).saldo==0 and consultar(db,itens).situacao=='fechado'
    assert contagens(pg)==(2,0,1)


def test_base_bruta_acima_limite_nao_quebra_total_liquido_valido(runtime_pg,pg,itens):
    with pg.begin() as c:
        c.execute(text("UPDATE itens_comanda SET quantidade=2,preco_unitario=99999999.99,desconto_tipo='cortesia' WHERE id=:item"),itens)
    with Session(runtime_pg) as db:
        p,d=preparar(db,itens,dados(itens,'nenhum','0','encerramento_gratuito'))
        assert p.posterior.total==0 and p.posterior.total_bruto==Decimal('199999999.98')
        assert p.model_dump(mode='json')['posterior']['total_bruto']=='199999999.98'
        r=aplicar(db,itens,d.model_copy(update={'confirmar_gratuidade':True}));assert r.fechado
    assert contagens(pg)==(0,0,1)


def test_replay_inclusao_preserva_resposta_apos_cortesia(runtime_pg,pg,itens):
    s=itens;key=uuid4()
    with Session(runtime_pg) as db:
        original=incluir(db,s,quantidade=1,chave_idempotencia=key)
        alvo=s|{'item':original.item.id}
        _,d=preparar(db,alvo,dados(alvo,'cortesia','0',versao=1));aplicar(db,alvo,d)
        assert consultar(db,s).total==30
        assert incluir(db,s,quantidade=1,chave_idempotencia=key)==original
        assert original.total==60 and original.item.preco_unitario==30


def test_inclusao_excedendo_limite_reverte_sem_auditoria(runtime_pg,pg,itens):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with pg.begin() as c:c.execute(text('UPDATE servicos SET preco=99999999.99 WHERE id=:service'),itens)
    with Session(runtime_pg) as db:
        with pytest.raises(EntradaFinanceiraInvalida):incluir(db,itens,quantidade=2)
        assert consultar(db,itens).total==30
    with pg.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM itens_comanda'))==1
        assert c.scalar(text('SELECT count(*) FROM inclusoes_servicos_comanda'))==0
