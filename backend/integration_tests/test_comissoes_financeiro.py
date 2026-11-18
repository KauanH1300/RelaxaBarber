from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_financeiro_servicos import caso
from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_http import api, requisitar, pagamento
from test_alteracoes_itens import itens
from test_itens_comanda import aberta


def test_snapshot_pagamento_estorno_e_repeticao(api, runtime_pg, pg, caso):
    from app.models import Comanda, ItemComanda, Servico, EventoComissao
    from app.services import comissoes
    with pg.begin() as c:
        servico=c.scalar(text('SELECT id FROM servicos LIMIT 1'))
        c.execute(text('UPDATE servicos SET comissao_padrao=20 WHERE id=:id'), {'id':servico})
        c.execute(text('UPDATE comandas SET comissoes_ativas=true WHERE id=:id'), {'id':caso['comanda']})
        c.execute(text('UPDATE itens_comanda SET servico_id=:servico WHERE comanda_id=:comanda'), {'servico':servico,'comanda':caso['comanda']})
    with Session(runtime_pg) as db:
        comanda=db.get(Comanda,caso['comanda']); item=db.scalar(select(ItemComanda).where(ItemComanda.comanda_id==comanda.id))
        comissoes.fixar(db,comanda,item,comanda.barbeiro_id);comissoes.registrar(db,comanda,Decimal('0.00'),'inclusao',caso['atores']['admin']);db.commit()
    with pg.begin() as c: c.execute(text('UPDATE servicos SET comissao_padrao=50 WHERE id=:id'), {'id':servico})
    chave=uuid4(); body={'pagamentos':[pagamento(valor='10.00')|{'confirmado':True}]}
    r=requisitar(api,caso,'recebimentos',body=body,key=chave); assert r[0]==200, r
    assert requisitar(api,caso,'recebimentos',body=body,key=chave)==r
    with Session(pg) as db:
        eventos=db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==caso['comanda']).order_by(EventoComissao.ordem)).all()
        assert len(eventos)==2 and eventos[-1].percentual==20 and eventos[-1].base==Decimal('30.50') and eventos[-1].chave_operacao==chave
        assert eventos[-1].gerada==Decimal('6.10') and eventos[-1].liberada==Decimal('2.00') and eventos[-1].paga==0
    estorno={'pagamento_id':r[1][0]['id'],'valor':'5.00','motivo':'Correção teste','efetivado_em':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
    r2=requisitar(api,caso,'estornos',perfil='admin',body=estorno,key=uuid4());assert r2[0]==200,r2
    with Session(pg) as db:
        eventos=db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==caso['comanda']).order_by(EventoComissao.ordem)).all()
        assert len(eventos)==3 and eventos[-1].gerada==Decimal('6.10') and eventos[-1].liberada==Decimal('1.00')
    from app.api.routes.comissoes import resumo_comanda
    from app.models import Usuario
    from fastapi import HTTPException
    import pytest
    with Session(runtime_pg) as db:
        resultado=resumo_comanda(caso['comanda'],caso['filial'],db,db.get(Usuario,caso['atores']['barbeiro']))
        assert resultado.verificado and resultado.gerada==Decimal('6.10') and resultado.liberada==Decimal('1.00') and resultado.paga==0
        with pytest.raises(HTTPException) as erro: resumo_comanda(caso['comanda'],caso['filial'],db,db.get(Usuario,caso['atores']['recepcao']))
        assert erro.value.status_code==403


def test_pagamentos_concorrentes_nao_duplicam_liberacao(runtime_pg, pg, caso):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from app.models import Comanda, ItemComanda, Usuario, EventoComissao
    from app.services import comissoes
    from app.services.financeiro import registrar_recebimentos
    with pg.begin() as c:
        c.execute(text('UPDATE servicos SET comissao_padrao=20 WHERE id=:service'),caso)
        c.execute(text('UPDATE comandas SET comissoes_ativas=true WHERE id=:comanda'),caso)
        c.execute(text('UPDATE itens_comanda SET servico_id=:service WHERE comanda_id=:comanda'),caso)
    with Session(runtime_pg) as db:
        command=db.get(Comanda,caso['comanda']);item=db.scalar(select(ItemComanda).where(ItemComanda.comanda_id==command.id))
        comissoes.fixar(db,command,item,command.barbeiro_id);comissoes.registrar(db,command,Decimal('0'),'inclusao',caso['atores']['admin']);db.commit()
    barrier=Barrier(2)
    def executar(_):
        with Session(runtime_pg) as db:
            usuario=db.get(Usuario,caso['atores']['recepcao']);barrier.wait()
            return registrar_recebimentos(caso['comanda'],pagamentos=[{'valor':Decimal('5'), 'forma':'pix','recebido_em':datetime.now(timezone.utc)-timedelta(minutes=1),'confirmado':True}],chave_idempotencia=uuid4(),db=db,usuario=usuario,filial_id=caso['filial'])
    with ThreadPoolExecutor(max_workers=2) as pool: assert len(list(pool.map(executar,range(2))))==2
    with Session(pg) as db:
        eventos=db.scalars(select(EventoComissao).order_by(EventoComissao.ordem)).all()
        assert len(eventos)==3 and [e.liberada for e in eventos]==[Decimal('0'),Decimal('1'),Decimal('2')]


def test_desconto_geral_e_cortesia_recalculam_comissao(runtime_pg, pg, itens):
    from app.models import Comanda, ItemComanda, EventoComissao, Usuario, PagamentoComanda
    from app.services import comissoes
    from app.services.financeiro import registrar_estorno
    from test_alteracoes_itens import receber
    from test_beneficios import dados, preparar, aplicar
    with pg.begin() as c:
        c.execute(text('UPDATE comandas SET comissoes_ativas=true WHERE id=:comanda'),itens)
        c.execute(text('UPDATE servicos SET comissao_padrao=20 WHERE id=:service'),itens)
    with Session(runtime_pg,expire_on_commit=False) as db:
        command=db.get(Comanda,itens['comanda']);item=db.get(ItemComanda,itens['item'])
        comissoes.fixar(db,command,item,command.barbeiro_id);comissoes.registrar(db,command,Decimal('0'),'inclusao',itens['atores']['admin']);db.commit()
        receber(db,itens,'10')
        _,d=preparar(db,itens,dados(itens,'valor','5','comanda'));aplicar(db,itens,d)
        eventos=db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==command.id).order_by(EventoComissao.ordem)).all()
        assert (eventos[-1].base,eventos[-1].gerada,eventos[-1].liberada)==(Decimal('25'),Decimal('5'),Decimal('2'))
        pagamento=db.scalar(select(PagamentoComanda).where(PagamentoComanda.comanda_id==command.id))
        registrar_estorno(command.id,pagamento_id=pagamento.id,valor=Decimal('10'),motivo='Correção teste',efetivado_em=datetime.now(timezone.utc)-timedelta(seconds=1),chave_idempotencia=uuid4(),db=db,usuario=db.get(Usuario,itens['atores']['admin']),filial_id=itens['filial'])
        _,d=preparar(db,itens,dados(itens,'nenhum','0','comanda',1));aplicar(db,itens,d)
        _,d=preparar(db,itens,dados(itens,'cortesia','0','item',2));aplicar(db,itens,d)
        evento=db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==command.id).order_by(EventoComissao.ordem.desc())).first()
        assert (evento.base,evento.gerada,evento.liberada)==(Decimal('0'),Decimal('0'),Decimal('0'))


def test_comanda_legada_nao_gera_eventos(runtime_pg, pg, aberta):
    from app.models import EventoComissao
    from test_itens_comanda import incluir
    from test_alteracoes_itens import receber
    from app.api.routes.comissoes import resumo_comanda
    from app.models import Usuario
    with Session(runtime_pg,expire_on_commit=False) as db:
        incluir(db,aberta,quantidade=1)
        receber(db,aberta,'5')
        resumo=resumo_comanda(aberta['comanda'],aberta['filial'],db,db.get(Usuario,aberta['atores']['admin']))
        assert not resumo.verificado and resumo.itens==[] and resumo.gerada==resumo.liberada==resumo.paga==0
    with Session(pg) as db: assert db.scalars(select(EventoComissao)).all()==[]


def test_edicao_e_substituicao_preservam_snapshots(runtime_pg, pg, itens):
    from app.models import Comanda, ItemComanda, EventoComissao, ComissaoItem
    from app.services import comissoes
    from test_alteracoes_itens import dados, preparar, aplicar
    with pg.begin() as c:
        c.execute(text('UPDATE comandas SET comissoes_ativas=true WHERE id=:comanda'),itens)
        c.execute(text('UPDATE servicos SET comissao_padrao=20 WHERE id=:service'),itens)
        c.execute(text('UPDATE servicos SET comissao_padrao=40 WHERE id=:novo'),itens)
    with Session(runtime_pg,expire_on_commit=False) as db:
        command=db.get(Comanda,itens['comanda']);item=db.get(ItemComanda,itens['item'])
        comissoes.fixar(db,command,item,command.barbeiro_id);comissoes.registrar(db,command,Decimal('0'),'inclusao',itens['atores']['admin']);db.commit()
    with pg.begin() as c: c.execute(text('UPDATE servicos SET comissao_padrao=50 WHERE id=:service'),itens)
    with Session(runtime_pg,expire_on_commit=False) as db:
        _,d=preparar(db,itens,dados(itens|{'novo':itens['service']},acao='substituir',quantidade=2));aplicar(db,itens,d)
        assert db.get(ComissaoItem,itens['item']).percentual==Decimal('20')
        _,d=preparar(db,itens,dados(itens,acao='substituir',quantidade=1,versao=1));aplicar(db,itens,d)
        assert db.get(ComissaoItem,itens['item']).percentual==Decimal('40')
        eventos=db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==itens['comanda']).order_by(EventoComissao.ordem)).all()
        assert [e.percentual for e in eventos]==[Decimal('20'),Decimal('20'),Decimal('40')]
