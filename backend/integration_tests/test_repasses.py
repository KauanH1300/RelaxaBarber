from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso
from test_financeiro_http import api

INICIO, FIM = date(2099,1,1), date(2099,1,31)

@pytest.fixture
def pronto(runtime_pg,pg,caso):
    from app.models import Comanda, ItemComanda
    from app.services import comissoes
    with pg.begin() as c:
        c.execute(text('UPDATE servicos SET comissao_padrao=20 WHERE id=:service'),caso)
        c.execute(text('UPDATE comandas SET comissoes_ativas=true WHERE id=:comanda'),caso)
        c.execute(text('UPDATE itens_comanda SET servico_id=:service WHERE comanda_id=:comanda'),caso)
    with Session(runtime_pg) as db:
        command=db.get(Comanda,caso['comanda']);item=db.scalar(select(ItemComanda).where(ItemComanda.comanda_id==command.id))
        comissoes.fixar(db,command,item,command.barbeiro_id)
        comissoes.registrar(db,command,Decimal('10'),'recebimento',caso['atores']['admin'],uuid4());db.commit()
    return caso

def usuario(db,s,perfil='admin'):
    from app.models import Usuario
    return db.get(Usuario,s['atores'][perfil])

def test_fechamento_pagamento_estorno_e_complemento(runtime_pg,pg,pronto,api):
    from app.services import repasses,comissoes
    from app.models import Comanda
    s=pronto;chave=uuid4()
    from app.core.security import criar_token
    from test_seguranca_horarios import chamar
    def conferir(chave, sufixo='', perfil='admin'):
        async def com_header(scope, receive, send):
            scope = dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(chave).encode())])
            await api(scope, receive, send)
        return chamar(com_header, f"/repasses/profissionais/{s['user']}/operacao?filial_id={s['filial']}{sufixo}",
                      token=criar_token(s['atores'][perfil]))
    assert conferir(chave) == (200, {'id': None})
    assert conferir(chave, perfil='recepcao')[0] == 403
    with Session(runtime_pg,expire_on_commit=False) as db:
        ator=usuario(db,s)
        f=repasses.fechar(db,ator,s['filial'],s['user'],INICIO,FIM,chave)
        assert conferir(chave) == (200, f)
        assert repasses.fechar(db,ator,s['filial'],s['user'],INICIO,FIM,chave)==f
        resumo=repasses.consultar(db,ator,s['filial'],s['user'],INICIO,FIM)
        assert resumo['elegivel']==0 and resumo['parcelas'][0]['disponivel']==2
        data_pag=datetime.now(timezone.utc)-timedelta(seconds=5);pagkey=uuid4()
        p=repasses.pagar(db,ator,s['filial'],s['user'],UUID(f['id']),Decimal('1'),'pix',data_pag,pagkey)
        assert conferir(pagkey, '&fechamento_id=' + f['id']) == (200, p)
        assert repasses.pagar(db,ator,s['filial'],s['user'],UUID(f['id']),Decimal('1'),'pix',data_pag,pagkey)==p
        estkey=uuid4();e=repasses.estornar(db,ator,s['filial'],s['user'],UUID(f['id']),UUID(p['id']),Decimal('.50'),'Correção',estkey)
        assert conferir(estkey, '&fechamento_id=' + f['id'] + '&pagamento_id=' + p['id']) == (200, e)
        assert conferir(estkey, '&fechamento_id=' + f['id'] + '&pagamento_id=' + str(uuid4())) == (200, {'id': None})
        assert repasses.estornar(db,ator,s['filial'],s['user'],UUID(f['id']),UUID(p['id']),Decimal('.50'),'Correção',estkey)==e
        resumo=repasses.consultar(db,ator,s['filial'],s['user'],INICIO,FIM)
        assert resumo['parcelas'][0]['disponivel']==Decimal('1.50')
        from app.api.routes.comissoes import resumo_comanda
        assert resumo_comanda(s['comanda'],s['filial'],db,ator).paga==Decimal('.50')
    with Session(runtime_pg) as db:
        c=db.get(Comanda,s['comanda']);comissoes.registrar(db,c,Decimal('20'),'recebimento',s['atores']['admin'],uuid4());db.commit()
    with Session(runtime_pg) as db:
        ator=usuario(db,s);resumo=repasses.consultar(db,ator,s['filial'],s['user'],INICIO,FIM)
        assert resumo['elegivel']==2
        complemento=repasses.fechar(db,ator,s['filial'],s['user'],INICIO,FIM,uuid4())
        assert complemento!=f
        assert repasses.consultar(db,ator,s['filial'],s['user'],INICIO,FIM)['elegivel']==0

def test_fechamentos_concorrentes_nao_duplicam(runtime_pg,pronto):
    from app.services import repasses
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=pronto;barreira=Barrier(2)
    def executar(_):
        with Session(runtime_pg) as db:
            ator=usuario(db,s);barreira.wait()
            try:repasses.fechar(db,ator,s['filial'],s['user'],INICIO,FIM,uuid4());return 'ok'
            except EstadoFinanceiroIncompativel:return 'sem saldo'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(executar,range(2)))==['ok','sem saldo']

def test_permissoes_e_acl(runtime_pg,pg,pronto):
    from app.services import repasses
    from app.services.financeiro_errors import AcessoFinanceiroNegado
    s=pronto
    with Session(runtime_pg) as db:
        recepcao=usuario(db,s,'recepcao')
        with pytest.raises(AcessoFinanceiroNegado):repasses.consultar(db,recepcao,s['filial'],s['user'],INICIO,FIM)
        with pytest.raises(AcessoFinanceiroNegado):repasses.fechar(db,recepcao,s['filial'],s['user'],INICIO,FIM,uuid4())
        with pytest.raises(AcessoFinanceiroNegado):repasses.consultar(db,recepcao,s['outra_filial'],s['user'],INICIO,FIM)
    with pg.connect() as db:
        for role in ('anon','authenticated'):
            for table in ('fechamentos_repasse','parcelas_repasse','pagamentos_repasse','alocacoes_repasse','estornos_repasse','alocacoes_estorno_repasse'):
                assert not db.scalar(text("SELECT has_table_privilege(:role,:t,'SELECT') OR has_table_privilege(:role,:t,'INSERT')"),{'role':role,'t':'public.'+table})

def test_pagamentos_concorrentes_respeitam_saldo(runtime_pg,pronto):
    from app.services import repasses
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=pronto
    with Session(runtime_pg) as db:
        fechamento=UUID(repasses.fechar(db,usuario(db,s),s['filial'],s['user'],INICIO,FIM,uuid4())['id'])
    barreira=Barrier(2)
    def tentativa(_):
        with Session(runtime_pg) as db:
            ator=usuario(db,s);barreira.wait()
            try:
                repasses.pagar(db,ator,s['filial'],s['user'],fechamento,Decimal('1.50'),'dinheiro',datetime.now(timezone.utc)-timedelta(seconds=2),uuid4())
                return 'ok'
            except EstadoFinanceiroIncompativel:return 'sem saldo'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(tentativa,range(2)))==['ok','sem saldo']

def test_ajuste_negativo_apos_repasse_impede_credito_indevido(runtime_pg,pronto):
    from app.services import repasses,comissoes
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    from app.models import Comanda
    s=pronto
    with Session(runtime_pg,expire_on_commit=False) as db:
        ator=usuario(db,s);f=UUID(repasses.fechar(db,ator,s['filial'],s['user'],INICIO,FIM,uuid4())['id'])
        repasses.pagar(db,ator,s['filial'],s['user'],f,Decimal('2'),'pix',datetime.now(timezone.utc)-timedelta(seconds=2),uuid4())
    with Session(runtime_pg) as db:
        c=db.get(Comanda,s['comanda']);comissoes.registrar(db,c,Decimal('5'),'estorno',s['atores']['admin'],uuid4());db.commit()
    with Session(runtime_pg) as db:
        ator=usuario(db,s);resumo=repasses.consultar(db,ator,s['filial'],s['user'],INICIO,FIM)
        assert resumo['deficit_pago']==Decimal('1') and resumo['bloqueado'] and resumo['elegivel']==0
        with pytest.raises(EstadoFinanceiroIncompativel):repasses.fechar(db,ator,s['filial'],s['user'],INICIO,FIM,uuid4())

def test_api_autenticacao_e_perfis(api,pronto):
    from app.core.security import criar_token
    from test_seguranca_horarios import chamar
    s=pronto;rota=f"/repasses/profissionais/{s['user']}?filial_id={s['filial']}&inicio={INICIO}&fim={FIM}"
    assert chamar(api,rota)[0]==401
    assert chamar(api,rota,token=criar_token(s['atores']['admin']))[0]==200
    assert chamar(api,rota,token=criar_token(s['atores']['recepcao']))[0]==403
    assert chamar(api,rota,token=criar_token(s['atores']['barbeiro_chefe']))[0]==403
    from test_financeiro_http import requisitar
    assert requisitar(api,s,query=f"?filial_id={s['filial']}")[0]==200
    assert chamar(api,rota,token=criar_token(s['atores']['barbeiro']))[0]==403
    proibida=rota.replace(str(s['filial']),str(s['outra_filial']))
    assert chamar(api,proibida,token=criar_token(s['atores']['recepcao']))[0]==403

def test_recebimento_estorno_real_do_cliente_preserva_repasse(runtime_pg,pg,caso):
    from app.models import Comanda, ItemComanda
    from app.services import comissoes, financeiro, repasses
    s=caso
    with pg.begin() as db:
        db.execute(text("UPDATE comandas SET status='aberta',data_fechamento=NULL,comissoes_ativas=true WHERE id=:comanda"),s)
        db.execute(text('UPDATE servicos SET comissao_padrao=20 WHERE id=:service'),s)
        db.execute(text('UPDATE itens_comanda SET servico_id=:service WHERE comanda_id=:comanda'),s)
    with Session(runtime_pg,expire_on_commit=False) as db:
        c=db.get(Comanda,s['comanda']);item=db.scalar(select(ItemComanda).where(ItemComanda.comanda_id==c.id))
        comissoes.fixar(db,c,item,c.barbeiro_id);comissoes.registrar(db,c,Decimal('0'),'inclusao',s['atores']['admin'],uuid4());db.commit()
        instante=datetime.now(timezone.utc)-timedelta(minutes=1)
        pagamento=financeiro.registrar_recebimentos(s['comanda'],pagamentos=[{'valor':Decimal('10'),'forma':'pix','recebido_em':instante,'confirmado':True}],chave_idempotencia=uuid4(),db=db,usuario=usuario(db,s,'recepcao'),filial_id=s['filial'])[0]
        f=UUID(repasses.fechar(db,usuario(db,s),s['filial'],s['user'],INICIO,FIM,uuid4())['id'])
        p=UUID(repasses.pagar(db,usuario(db,s),s['filial'],s['user'],f,Decimal('2'),'pix',instante,uuid4())['id'])
        financeiro.registrar_estorno(s['comanda'],pagamento_id=pagamento.id,valor=Decimal('5'),motivo='Correção do cliente',efetivado_em=instante+timedelta(seconds=1),chave_idempotencia=uuid4(),db=db,usuario=usuario(db,s),filial_id=s['filial'])
        estado=repasses.consultar(db,usuario(db,s),s['filial'],s['user'],INICIO,FIM)
        assert estado['bloqueado'] and estado['deficit_pago']==Decimal('1')
        assert estado['pagamentos'][0]['id']==p and estado['pagamentos'][0]['valor']==Decimal('2')

def test_rececao_nao_registra_ou_estorna_repasse(runtime_pg,pronto):
    from app.services import repasses
    from app.services.financeiro_errors import AcessoFinanceiroNegado
    s=pronto;data_pag=datetime.now(timezone.utc)-timedelta(seconds=5)
    with Session(runtime_pg,expire_on_commit=False) as db:
        admin=usuario(db,s);f=UUID(repasses.fechar(db,admin,s['filial'],s['user'],INICIO,FIM,uuid4())['id'])
        p=UUID(repasses.pagar(db,admin,s['filial'],s['user'],f,Decimal('1'),'pix',data_pag,uuid4())['id'])
        recepcao=usuario(db,s,'recepcao')
        with pytest.raises(AcessoFinanceiroNegado):
            repasses.pagar(db,recepcao,s['filial'],s['user'],f,Decimal('1'),'pix',data_pag,uuid4())
        with pytest.raises(AcessoFinanceiroNegado):
            repasses.estornar(db,recepcao,s['filial'],s['user'],f,p,Decimal('1'),'Teste',uuid4())

def test_mesma_chave_concorrente_em_profissionais_distintos_e_conflito(runtime_pg,pg,pronto):
    from app.models import Comanda, ItemComanda
    from app.services import repasses,comissoes
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira
    from test_financeiro_persistencia import criar_comanda
    s=pronto
    with pg.begin() as conn:
        outro=criar_comanda(conn,s|{'user':s['other']},dia='2099-01-02',controle=True)
        conn.execute(text('UPDATE comandas SET comissoes_ativas=true WHERE id=:comanda'),outro)
        conn.execute(text('UPDATE itens_comanda SET servico_id=:service WHERE comanda_id=:comanda'),outro)
    with Session(runtime_pg) as db:
        c=db.get(Comanda,outro['comanda']);item=db.scalar(select(ItemComanda).where(ItemComanda.comanda_id==c.id))
        comissoes.fixar(db,c,item,c.barbeiro_id);comissoes.registrar(db,c,Decimal('10'),'recebimento',s['atores']['admin'],uuid4());db.commit()
    chave,barreira=uuid4(),Barrier(2)
    def executar(profissional):
        with Session(runtime_pg) as db:
            ator=usuario(db,s);barreira.wait()
            try:repasses.fechar(db,ator,s['filial'],profissional,INICIO,FIM,chave);return 'ok'
            except ConflitoIdempotenciaFinanceira:return 'conflito'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(executar,[s['user'],s['other']]))==['conflito','ok']
    with pg.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM fechamentos_repasse WHERE filial_id=:filial AND chave=:chave'),{'filial':s['filial'],'chave':chave})==1

def test_comissao_surgida_apos_selecao_das_travas_aguarda_proximo_fechamento(runtime_pg,pg,pronto):
    from app.models import Comanda, ItemComanda
    from app.services import repasses,comissoes
    from test_financeiro_persistencia import criar_comanda
    s=pronto
    with Session(runtime_pg) as db:
        bloqueadas=repasses._travar(db,s['filial'],s['user'])
        with pg.begin() as conn:
            novo=criar_comanda(conn,s,dia='2099-01-02',controle=True)
            conn.execute(text('UPDATE comandas SET comissoes_ativas=true WHERE id=:comanda'),novo)
            conn.execute(text('UPDATE itens_comanda SET servico_id=:service WHERE comanda_id=:comanda'),novo)
        with Session(runtime_pg) as outra:
            c=outra.get(Comanda,novo['comanda']);item=outra.scalar(select(ItemComanda).where(ItemComanda.comanda_id==c.id))
            comissoes.fixar(outra,c,item,c.barbeiro_id);comissoes.registrar(outra,c,Decimal('10'),'recebimento',s['atores']['admin'],uuid4());outra.commit()
        _,estavel=repasses._dados(db,s['filial'],s['user'],INICIO,FIM,bloqueadas)
        _,posterior=repasses._dados(db,s['filial'],s['user'],INICIO,FIM)
        assert estavel.elegivel_periodo==Decimal('2') and posterior.elegivel_periodo==Decimal('4')
        db.rollback()

def test_auditoria_tem_carimbo_do_banco_e_lancamentos_imutaveis(pg,pronto):
    from sqlalchemy.exc import DBAPIError
    s=pronto;ident=uuid4()
    with pg.begin() as db:
        db.execute(text('''INSERT INTO public.fechamentos_repasse(id,filial_id,profissional_id,inicio,fim,valor,registrado_por,registrado_em,chave,fingerprint)
            VALUES (:id,:filial,:profissional,:inicio,:fim,1,:ator,'2000-01-01T00:00:00Z',:chave,:fp)'''),
            dict(id=ident,filial=s['filial'],profissional=s['user'],inicio=INICIO,fim=FIM,ator=s['atores']['admin'],chave=uuid4(),fp='a'*64))
        assert db.scalar(text('SELECT extract(year FROM registrado_em) FROM public.fechamentos_repasse WHERE id=:id'),{'id':ident})>2000
        with pytest.raises(DBAPIError),db.begin_nested():
            db.execute(text('UPDATE public.fechamentos_repasse SET valor=2 WHERE id=:id'),{'id':ident})
