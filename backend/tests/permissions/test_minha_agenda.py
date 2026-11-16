from datetime import date,datetime,timezone
from decimal import Decimal
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,event
from test_portal_clientes import portal,ativar,cadastro,logar  # noqa:F401
from test_reserva_publica import reserva,api,dados  # noqa:F401


@pytest.fixture
def minha(reserva):
    p=reserva
    code,out,_=api(p,'/portal-clientes/reservas',dados(p),'POST');assert code==201
    p.id=UUID(out['id'])
    return p


def url(p,sufixo=''):return f'/portal-clientes/agendamentos/{p.id}'+sufixo
def atual(p):return api(p,url(p))[1]
def versao(p):return {'atualizado_em_esperado':atual(p)['atualizado_em']}
def remarca(p,**changes):return versao(p)|dict(data='2099-05-21',hora_inicio='10:00',barbeiro_id=str(p.b.id))|changes


def test_lista_autenticada_snapshots_e_campos_reduzidos(minha):
    p=minha;p.s.preco=90;p.s.tempo_estimado=90;p.db.commit()
    code,rows,_=api(p,'/portal-clientes/agendamentos?cliente_id='+str(uuid4()))
    assert code==200 and len(rows)==1
    r=rows[0];assert Decimal(r['valor'])==30 and r['duracao']==30 and r['proximo']
    assert r['pode_cancelar'] and r['pode_remarcar']
    assert not {'cliente_id','comanda','pagamentos','criado_por','observacoes','cancelado_por'}&set(r)
    assert api(p,'/portal-clientes/agendamentos',cookie=None)[0]==401


def test_outro_cliente_nao_acessa_nem_modifica(minha):
    p=minha;pedido=remarca(p)
    body,_=ativar(p,email='outrocliente@example.com',telefone='21988881234')
    token=logar(p,body)
    assert api(p,'/portal-clientes/agendamentos',cookie=token)[1]==[]
    for suffix,method,body in [('', 'GET',None),('/opcoes','GET',None),('/cancelamento','POST',versao(p)),('/reagendamento','PATCH',pedido)]:
        assert api(p,url(p,suffix),body,method,cookie=token)[0]==404


def test_cancelamento_reutiliza_status_e_preserva_historico(minha):
    from app.models import Agendamento,Comanda
    p=minha;a=p.db.get(Agendamento,p.id);c=p.db.scalar(select(Comanda));cid=c.id
    payload=versao(p)
    assert api(p,url(p,'/cancelamento'),payload,'POST')[0]==200
    p.db.refresh(a);p.db.refresh(c)
    assert a.status=='cancelado' and c.status=='cancelada' and c.id==cid and len(c.itens)==1
    assert a.cancelado_por is None and a.cancelado_por_cliente==a.cliente_id and a.cancelado_em
    assert not atual(p)['proximo'] and not atual(p)['pode_cancelar']
    assert api(p,url(p,'/cancelamento'),payload,'POST')[0]==409


@pytest.mark.parametrize('estado',['concluido','cancelado','em_atendimento','passado','iniciado'])
def test_estados_e_passado_bloqueiam_ambas_operacoes(minha,estado,monkeypatch):
    from app.models import Agendamento
    from app.services import agendamento
    p=minha;a=p.db.get(Agendamento,p.id)
    if estado=='passado':a.data=date(2000,1,1)
    elif estado=='iniciado':
        from datetime import time
        monkeypatch.setattr(agendamento,'agora_local',lambda:datetime(2099,5,20,12,tzinfo=agendamento.FUSO_BARBEARIA))
        a.data=date(2099,5,20);a.hora_inicio=time(11);a.hora_fim=time(13)
    else:a.status=estado
    p.db.commit();assert not atual(p)['pode_cancelar']
    assert api(p,url(p,'/cancelamento'),versao(p),'POST')[0]==409
    assert api(p,url(p,'/reagendamento'),remarca(p),'PATCH')[0]==409


def test_remarca_preserva_ids_valores_e_autoria_cliente(minha):
    from app.models import Agendamento,Comanda,Reagendamento
    p=minha;a=p.db.get(Agendamento,p.id);c=p.db.scalar(select(Comanda));cid=c.id;cliente=a.cliente_id
    payload=remarca(p)
    assert api(p,url(p,'/reagendamento'),payload,'PATCH')[0]==200
    p.db.refresh(c);p.db.refresh(a)
    assert a.id==p.id and a.cliente_id==cliente and a.barbeiro_id==p.b.id
    # PostgreSQL verifies the existing FK cascade; SQLite fixture may enable it as well.
    assert c.id==cid and Decimal(c.valor_total)==30 and len(a.servicos)==len(c.itens)==1
    hist=p.db.scalar(select(Reagendamento));assert hist.registrado_por is None and hist.registrado_por_cliente==cliente
    assert hist.data_anterior==date(2099,5,20) and hist.data_nova==date(2099,5,21)
    assert api(p,url(p,'/reagendamento'),payload,'PATCH')[0]==409


def test_disponibilidade_usa_duracao_snapshot_e_ignora_propria_reserva(minha):
    p=minha;p.s.tempo_estimado=120;p.db.commit()
    code,out,_=api(p,url(p,f'/opcoes?data=2099-05-20&barbeiro_id={p.a.id}'))
    assert code==200 and '09:00' in out['horarios'] and '17:30' in out['horarios']
    assert all(set(b)=={'id','nome'} for b in out['barbeiros'])


def test_restricoes_e_ocupacao_revalidadas_qualquer_barbeiro(minha):
    from app.models.reserva_portal import RestricaoServico
    p=minha;p.db.add(RestricaoServico(filial_id=p.f.id,barbeiro_id=p.b.id,servico_id=p.s.id));p.db.commit()
    assert api(p,url(p,'/reagendamento'),remarca(p),'PATCH')[0]==409
    code,out,_=api(p,url(p,'/reagendamento'),remarca(p,barbeiro_id=None),'PATCH')
    assert code==200 and out['barbeiro']['id']==str(p.a.id)


def test_financeiro_com_pagamento_bloqueia_sem_alteracao(minha):
    from app.models import Comanda
    from app.models.financeiro import ControleFinanceiroComanda,PagamentoComanda
    p=minha;c=p.db.scalar(select(Comanda))
    p.db.add(ControleFinanceiroComanda(comanda_id=c.id,filial_id=p.f.id,registrado_por=p.admin.id,motivo='Teste'));p.db.flush()
    p.db.add(PagamentoComanda(comanda_id=c.id,filial_id=p.f.id,valor=Decimal('1.00'),forma='pix',recebido_em=datetime.now(timezone.utc),registrado_por=p.admin.id,chave_idempotencia=uuid4(),fingerprint='a'*64));p.db.commit()
    assert not atual(p)['pode_cancelar']
    assert api(p,url(p,'/cancelamento'),versao(p),'POST')[0]==409
    assert api(p,url(p,'/reagendamento'),remarca(p),'PATCH')[0]==409
    assert p.db.query(PagamentoComanda).count()==1 and p.db.scalar(select(Comanda.status))=='pendente'


def test_csrf_identidades_forjadas_e_versao(minha):
    from app.core.security import criar_token
    p=minha
    assert api(p,url(p,'/cancelamento'),versao(p),'POST',origin='https://hostil.example')[0]==403
    assert api(p,url(p,'/cancelamento'),versao(p),'POST',cookie=criar_token(p.admin.id))[0]==401
    assert api(p,url(p,'/reagendamento'),remarca(p)|{'cliente_id':str(uuid4())},'PATCH')[0]==422
    assert api(p,url(p,'/cancelamento'),versao(p)|{'status':'concluido'},'POST')[0]==422
    assert api(p,url(p,'/cancelamento'),{'atualizado_em_esperado':'2000-01-01T00:00:00Z'},'POST')[0]==409


def test_falha_de_commit_reverte_cancelamento(minha):
    from app.services import minha_agenda
    from app.schemas.minha_agenda import OperacaoAgendaCliente
    from app.models import Agendamento,Comanda
    p=minha;payload=OperacaoAgendaCliente(**versao(p))
    def falhar(session):raise RuntimeError('falha injetada')
    event.listen(p.db,'before_commit',falhar)
    try:
        with pytest.raises(RuntimeError):minha_agenda.cancelar(p.db,p.token,p.id,payload)
    finally:event.remove(p.db,'before_commit',falhar)
    assert p.db.get(Agendamento,p.id).status=='pendente' and p.db.scalar(select(Comanda.status))=='pendente'
