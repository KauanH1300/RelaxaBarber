"""Novas regras em PostgreSQL descartável, incluindo o login restrito real."""
from conftest import versao_agendamento
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso, ator, disputar, consultar, contagens
from test_financeiro_http import api, requisitar, pagamento


@pytest.fixture
def aberta(pg, caso):
    with pg.begin() as c:
        c.execute(text("UPDATE comandas SET status='aberta',data_fechamento=NULL WHERE id=:comanda"), caso)
        c.execute(text("UPDATE agendamentos SET status='em_atendimento' WHERE id=:agendamento"), caso)
    return caso


def receber(db, s, valor='10.00', key=None, perfil='recepcao', parcelas=None):
    from app.services.financeiro import registrar_recebimentos
    return registrar_recebimentos(s['comanda'], db=db, usuario=ator(db, s, perfil),
        filial_id=s['filial'], chave_idempotencia=key or uuid4(),
        pagamentos=parcelas if parcelas is not None else [dict(valor=Decimal(valor), forma='dinheiro',
            recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1), confirmado=True)])


@pytest.mark.parametrize('estado', ['em_atendimento', 'concluido'])
def test_parciais_quitacao_e_replay_original(runtime_pg, pg, aberta, estado):
    from app.models import Agendamento, Comanda
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira, EstadoFinanceiroIncompativel
    s=aberta; key=uuid4()
    with pg.begin() as c:c.execute(text('UPDATE agendamentos SET status=:status WHERE id=:agendamento'),s|{'status':estado})
    parcelas=[dict(valor=Decimal('10'),forma='dinheiro',recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1),confirmado=True)]
    with Session(runtime_pg) as db:
        first=receber(db,s,key=key,parcelas=parcelas)
        res=consultar(db,s);assert res.saldo==Decimal('20.50') and res.situacao=='aberto'
        assert db.get(Comanda,s['comanda']).status=='aberta'
        receber(db,s,'20.50')
        res=consultar(db,s);assert res.saldo==0 and res.situacao=='fechado'
        assert db.get(Agendamento,s['agendamento']).status==estado
        assert db.get(Comanda,s['comanda']).status=='fechada'
        assert receber(db,s,key=key,parcelas=parcelas)==first
        with pytest.raises(ConflitoIdempotenciaFinanceira):receber(db,s,key=key,parcelas=[parcelas[0]|{'valor':Decimal('11')}])
        with pytest.raises(EstadoFinanceiroIncompativel):receber(db,s,'1')
    assert contagens(pg)==(2,0,1)


@pytest.mark.parametrize('perfil',['admin','recepcao','barbeiro','barbeiro_chefe'])
def test_http_confirmacao_perfis_e_saldo(api,pg,aberta,perfil):
    s=aberta
    if perfil=='barbeiro_chefe':
        with pg.begin() as c:c.execute(text("UPDATE usuarios SET perfil='BARBEIRO_CHEFE' WHERE id=:user"),s)
        s['atores'][perfil]=s['user']
    body={'pagamentos':[pagamento(valor='10.00')|{'confirmado':True}]};key=uuid4()
    def post(p=body,k=key):return requisitar(api,s,'recebimentos',perfil=perfil,body=p,key=k)
    r=post();assert r[0]==200 and len(r[1])==1 and r[1][0]['valor']=='10.00'
    assert post()==r
    assert requisitar(api,s,perfil=perfil)[1]['saldo']=='20.50'
    assert post({'pagamentos':[body['pagamentos'][0]|{'valor':'11.00'}]})[0]==409
    assert post({'pagamentos':[pagamento(valor='20.51')|{'confirmado':True}]},uuid4())[0]==409
    assert contagens(pg)==(1,0,0)


@pytest.mark.parametrize('mudanca',[{}, {'confirmado':False}, {'confirmado':'true'}, {'confirmado':1}])
def test_sem_confirmacao_explicita_nao_recebe(api,pg,aberta,mudanca):
    p=pagamento()|mudanca
    r=requisitar(api,aberta,'recebimentos',body={'pagamentos':[p]},key=uuid4())
    assert r[0]==422 and contagens(pg)==(0,0,0)


@pytest.mark.parametrize('modo',['outra_filial','outro_profissional','sem_sessao','cancelada','pendente','nao_verificada'])
def test_elegibilidade(api,pg,aberta,modo):
    s=aberta;args={};status=409
    if modo=='outra_filial':args['query']='?filial_id='+str(s['outra_filial']);status=404
    elif modo=='outro_profissional':args['perfil']='outro';status=404
    elif modo=='sem_sessao':args['token']='';status=401
    else:
        with pg.begin() as c:
            if modo=='nao_verificada':
                # Nova comanda sem controle, em vez de apagar histórico imutável.
                from test_financeiro_persistencia import criar_comanda
                s=s|criar_comanda(c,s,dia='2099-01-02')
            else:c.execute(text('UPDATE comandas SET status=:status WHERE id=:comanda'),s|{'status':'cancelada' if modo=='cancelada' else 'pendente'})
    r=requisitar(api,s,'recebimentos',body={'pagamentos':[pagamento()|{'confirmado':True}]},key=uuid4(),**args)
    assert r[0]==status and contagens(pg)==(0,0,0)


def test_total_zero_nao_fecha(runtime_pg,pg,aberta):
    from app.services.financeiro import fechar_comanda
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel, SaldoInsuficiente
    with pg.begin() as c:c.execute(text('UPDATE itens_comanda SET preco_unitario=0 WHERE comanda_id=:comanda'),aberta)
    with Session(runtime_pg) as db:
        assert consultar(db,aberta).situacao=='aberto'
        with pytest.raises(SaldoInsuficiente):receber(db,aberta,'0.01')
        with pytest.raises(EstadoFinanceiroIncompativel):fechar_comanda(aberta['comanda'],db=db,usuario=ator(db,aberta),chave_idempotencia=uuid4(),motivo='Gratuidade')
    assert contagens(pg)==(0,0,0)


@pytest.mark.parametrize('etapa',['recebimento','fechamento'])
def test_falha_reverte_pagamento_e_fechamento(runtime_pg,pg,aberta,etapa):
    def falhar(c,cursor,sql,params,context,many):
        target='INSERT INTO '+('pagamentos_comanda' if etapa=='recebimento' else 'fechamentos_financeiros_comanda')
        if sql.startswith(target):raise RuntimeError('Falha ficticia')
    event.listen(runtime_pg,'before_cursor_execute',falhar)
    try:
        with Session(runtime_pg) as db,pytest.raises(RuntimeError):receber(db,aberta,'30.50')
    finally:event.remove(runtime_pg,'before_cursor_execute',falhar)
    assert contagens(pg)==(0,0,0)
    with pg.connect() as c:assert c.scalar(text('SELECT status FROM comandas WHERE id=:comanda'),aberta)=='aberta'


@pytest.mark.parametrize('commit_real',[False,True])
def test_resposta_perdida_recupera_mesma_operacao(pg,aberta,commit_real):
    from app.services.persistencia import ConfirmacaoIndeterminada
    class Incerta(Session):
        def commit(self):
            if commit_real:super().commit()
            raise OperationalError(None,{},SimpleNamespace(pgcode='08006'),connection_invalidated=True)
    p=[dict(valor=Decimal('30.50'),forma='pix',recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1),confirmado=True)];key=uuid4()
    with Incerta(pg) as db,pytest.raises(ConfirmacaoIndeterminada):receber(db,aberta,key=key,parcelas=p)
    with Session(pg) as db:
        r=receber(db,aberta,key=key,parcelas=p);assert receber(db,aberta,key=key,parcelas=p)==r
    assert contagens(pg)==(1,0,1)


@pytest.mark.parametrize('modo',['replay','parciais','excedente','conflito','fechamento_legado','inclusao'])
def test_concorrencia_locks_reais(runtime_pg,pg,aberta,modo):
    from app.services.financeiro import fechar_comanda
    from app.services.itens_comanda import adicionar_servico
    from app.services.financeiro_errors import SaldoInsuficiente, ConflitoIdempotenciaFinanceira, EstadoFinanceiroIncompativel
    s=aberta;key=uuid4();p=[dict(valor=Decimal('10'),forma='dinheiro',recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1),confirmado=True)]
    first=lambda db:receber(db,s,key=key,parcelas=p)
    if modo=='replay':second=lambda db:receber(db,s,key=key,parcelas=p)
    elif modo=='parciais':second=lambda db:receber(db,s,'20.50')
    elif modo=='conflito':second=lambda db:receber(db,s,key=key,parcelas=[p[0]|{'valor':Decimal('11')}])
    elif modo=='fechamento_legado':second=lambda db:fechar_comanda(s['comanda'],db=db,usuario=ator(db,s),chave_idempotencia=uuid4(),pagamentos=[p[0]|{'valor':Decimal('30.50')}])
    elif modo=='inclusao':
        first=lambda db:receber(db,s,'30.50')
        second=lambda db:adicionar_servico(s['comanda'],servico_id=s['service'],quantidade=1,chave_idempotencia=uuid4(),db=db,usuario=ator(db,s))
    else:second=lambda db:receber(db,s,'30.50')
    one,two=disputar(runtime_pg,first,second)
    if modo=='replay':assert one==two
    elif modo in ('excedente','fechamento_legado'):assert isinstance(two,SaldoInsuficiente)
    elif modo=='conflito':assert isinstance(two,ConflitoIdempotenciaFinanceira)
    elif modo=='inclusao':assert isinstance(two,EstadoFinanceiroIncompativel)
    assert contagens(pg)==((2,0,1) if modo=='parciais' else (1,0,1) if modo=='inclusao' else (1,0,0))


def test_atendimento_continua_apos_quitacao(runtime_pg,pg,aberta):
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.models import Comanda
    s=aberta
    with Session(runtime_pg) as db:
        receber(db,s,'30.50');comanda=db.get(Comanda,s['comanda']);when=comanda.data_fechamento
        for estado in ['concluido']:
            result=atualizar_status(s['agendamento'],AgendamentoStatusUpdate(status=estado, confirmado=True, atualizado_em_esperado=versao_agendamento(db, s['agendamento']), motivo_cancelamento=('Cancelamento fictício conferido' if estado == 'cancelado' else None)),db,ator(db,s),s['filial'])
            assert result.status==estado
            db.expire_all();comanda=db.get(Comanda,s['comanda'])
            assert comanda.status=='fechada' and comanda.data_fechamento==when
    assert contagens(pg)==(1,0,1)


@pytest.mark.parametrize('primeiro',['atendimento','pagamento'])
def test_quitacao_concorrente_com_avanco_operacional(runtime_pg,pg,aberta,primeiro):
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    advance=lambda db:atualizar_status(aberta['agendamento'],AgendamentoStatusUpdate(status='concluido'),db,ator(db,aberta),aberta['filial'])
    pay=lambda db:receber(db,aberta,'30.50')
    disputar(runtime_pg,advance if primeiro=='atendimento' else pay,pay if primeiro=='atendimento' else advance)
    with pg.connect() as c:
        assert c.scalar(text('SELECT status FROM agendamentos WHERE id=:agendamento'),aberta)=='concluido'
        assert c.scalar(text('SELECT status FROM comandas WHERE id=:comanda'),aberta)=='fechada'
    assert contagens(pg)==(1,0,1)


def test_multiplas_formas_replay_ordem_e_atomicidade(api,pg,aberta):
    body={'pagamentos':[pagamento(valor='10.00',forma='dinheiro')|{'confirmado':True},pagamento(valor='20.50',forma='credito')|{'confirmado':True}]};key=uuid4()
    r=requisitar(api,aberta,'recebimentos',body=body,key=key)
    assert r[0]==200 and len(r[1])==2
    assert requisitar(api,aberta,'recebimentos',body=body,key=key)==r
    assert requisitar(api,aberta,'recebimentos',body={'pagamentos':list(reversed(body['pagamentos']))},key=key)[0]==409
    assert requisitar(api,aberta)[1]['situacao']=='fechado'
    assert contagens(pg)==(2,0,1)


@pytest.mark.parametrize('valor',['10.00','30.50'])
def test_cancelamento_com_recebimento_nao_apaga_financeiro(runtime_pg,pg,aberta,valor):
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.errors import ConflitoEstadoAgendamento
    with Session(runtime_pg) as db:
        receber(db,aberta,valor)
        with pytest.raises(ConflitoEstadoAgendamento):atualizar_status(aberta['agendamento'],AgendamentoStatusUpdate(status='cancelado',motivo_cancelamento='Fixture', confirmado=True, atualizado_em_esperado=versao_agendamento(db, aberta['agendamento'])),db,ator(db,aberta),aberta['filial'])
    assert contagens(pg)==(1,0,0 if valor=='10.00' else 1)
