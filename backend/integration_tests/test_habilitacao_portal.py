"""Habilitacao real somente no PostgreSQL descartavel autorizado pelo conftest."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from test_financeiro_persistencia import data, criar_comanda
from test_financeiro_servicos import ator, disputar
from test_financeiro_http import api, requisitar


@pytest.fixture
def portal(pg, data):
    from app.models import Usuario, PerfilEnum, UsuarioFilial, ReservaPortal, Filial
    with Session(pg) as db:
        s = criar_comanda(db.connection(), data)
        db.execute(text("UPDATE agendamentos SET origem='portal_cliente',criado_por=NULL WHERE id=:agendamento"), s)
        db.execute(text("UPDATE comandas SET status='aberta',data_fechamento=NULL WHERE id=:comanda"), s)
        db.execute(text('UPDATE itens_comanda SET servico_id=:service'), s)
        db.add(ReservaPortal(cliente_id=s['client'],chave=uuid4(),fingerprint='a'*64,agendamento_id=s['agendamento']))
        atores = {'barbeiro':s['user']}
        for perfil in ['admin','recepcao','barbeiro_chefe']:
            u=Usuario(nome=perfil,email=perfil+'@habilitacao.example.test',senha_hash='ficticio',perfil=PerfilEnum(perfil))
            db.add(u);db.flush()
            db.add(UsuarioFilial(usuario_id=u.id,filial_id=s['filial']))
            atores[perfil]=u.id
        outra=Filial(nome='Outra ficticia',empresa_id=db.get(Filial,s['filial']).empresa_id)
        db.add(outra);db.flush();outra_id=outra.id
        db.commit()
    return s|{'atores':atores,'outra_filial':outra_id}


def resumo(db,s,perfil='recepcao'):
    from app.services.financeiro import consultar_situacao
    return consultar_situacao(s['comanda'],db,ator(db,s,perfil),s['filial'])


def body(engine,s):
    with Session(engine) as db:
        conf=resumo(db,s).habilitacao
        assert conf is not None
        return dict(conferencia=conf['conferencia'],confirmado=True,motivo='Origem, itens e valores conferidos')


def habilitar(db,s,payload,key,perfil='recepcao'):
    from app.services.habilitacao_financeira import habilitar as executar
    return executar(s['comanda'],**payload,chave_idempotencia=key,db=db,usuario=ator(db,s,perfil),filial_id=s['filial'])


def snapshot(engine):
    with engine.connect() as c:
        return {t:list(c.scalars(text(f'SELECT to_jsonb(t)::text FROM {t} t ORDER BY id'))) for t in ['agendamentos','comandas','itens_comanda']}


@pytest.mark.parametrize('perfil',['admin','recepcao'])
def test_http_habilita_sem_cobrar_preserva_dados_e_replay(api,pg,runtime_pg,portal,perfil):
    s=portal;p=body(runtime_pg,s);key=uuid4();antes=snapshot(pg)
    r=requisitar(api,s,'habilitacao-financeira',perfil=perfil,body=p,key=key)
    assert r[0]==200,r
    assert r[1]['registrado_por']==str(s['atores'][perfil]) and r[1]['registrado_em']
    assert requisitar(api,s,'habilitacao-financeira',perfil=perfil,body=p,key=key)==r
    assert snapshot(pg)==antes
    with Session(runtime_pg) as db:
        res=resumo(db,s)
        assert res.situacao=='aberto' and res.saldo==Decimal('30.50') and res.recebido_liquido==0
        assert res.habilitado_por==s['atores'][perfil]
    with pg.connect() as c:
        for t in ['pagamentos_comanda','estornos_pagamento','fechamentos_financeiros_comanda']:
            assert c.scalar(text(f'SELECT count(*) FROM {t}'))==0
    assert requisitar(api,s,'habilitacao-financeira',body=p,key=uuid4())[0]==409
    assert requisitar(api,s,'habilitacao-financeira',body=p|{'motivo':'Diferente'},key=key)[0]==409


@pytest.mark.parametrize('perfil',['barbeiro','barbeiro_chefe'])
def test_perfis_nao_gestores_nao_podem_habilitar(api,pg,runtime_pg,portal,perfil):
    s=portal;p=body(runtime_pg,s)
    if perfil=='barbeiro_chefe':
        with pg.begin() as c:c.execute(text("UPDATE usuarios SET perfil='BARBEIRO_CHEFE' WHERE id=:user"),s)
        s['atores'][perfil]=s['user']
    with Session(runtime_pg) as db:assert resumo(db,s,perfil).habilitacao is None
    assert requisitar(api,s,'habilitacao-financeira',perfil=perfil,body=p,key=uuid4())[0] in (403,404)


@pytest.mark.parametrize('modo',['cancelada','fechada','legado','autor_funcionario','sem_prova','sem_itens','valor_divergente','cancelado','filial','inativo'])
def test_bloqueios_preservam_ausencia_de_controle(api,pg,runtime_pg,portal,modo):
    s=portal;p=body(runtime_pg,s)
    sql={
        'cancelada':"UPDATE comandas SET status='cancelada'",
        'fechada':"UPDATE comandas SET status='fechada'",
        'legado':"UPDATE agendamentos SET origem='recepcao'",
        'autor_funcionario':'UPDATE agendamentos SET criado_por=:user',
        'sem_prova':'DELETE FROM portal_clientes_reservas',
        'sem_itens':'DELETE FROM itens_comanda',
        'valor_divergente':'UPDATE comandas SET valor_total=1',
        'cancelado':"UPDATE agendamentos SET status='cancelado'",
        'filial':"UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:recepcao",
        'inativo':"UPDATE usuarios SET ativo=false WHERE id=:recepcao"}[modo]
    with pg.begin() as c:c.execute(text(sql),s|{'recepcao':s['atores']['recepcao']})
    assert requisitar(api,s,'habilitacao-financeira',body=p,key=uuid4())[0] in (401,403,404,409)
    with pg.connect() as c:assert c.scalar(text('SELECT count(*) FROM controles_financeiros_comanda'))==0


def test_outra_filial_payload_invalido_e_conferencia_desatualizada(api,pg,runtime_pg,portal):
    s=portal;p=body(runtime_pg,s)
    assert requisitar(api,s,'habilitacao-financeira',body=p,key=uuid4(),query='?filial_id='+str(s['outra_filial']))[0] in (403,404)
    for mudanca in [{'confirmado':False},{'motivo':' '},{'conferencia':'invalida'},{'cliente_id':str(s['client'])}]:
        assert requisitar(api,s,'habilitacao-financeira',body=p|mudanca,key=uuid4())[0]==422
    with pg.begin() as c:c.execute(text("UPDATE itens_comanda SET descricao='Alterado'"))
    assert requisitar(api,s,'habilitacao-financeira',body=p,key=uuid4())[0]==409
    with pg.connect() as c:assert c.scalar(text('SELECT count(*) FROM controles_financeiros_comanda'))==0


@pytest.mark.parametrize('mesma_chave',[True,False])
def test_concorrencia_uma_unica_habilitacao(pg,runtime_pg,portal,mesma_chave):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=portal;p=body(runtime_pg,s);key=uuid4()
    um,dois=disputar(runtime_pg,lambda db:habilitar(db,s,p,key),lambda db:habilitar(db,s,p,key if mesma_chave else uuid4(),'admin'))
    assert um==dois if mesma_chave else isinstance(dois,EstadoFinanceiroIncompativel)
    with pg.connect() as c:assert c.scalar(text('SELECT count(*) FROM controles_financeiros_comanda'))==1


def test_falha_antes_commit_reverte_controle(pg,runtime_pg,portal):
    from app.services.persistencia import FalhaPersistencia
    s=portal;p=body(runtime_pg,s);antes=snapshot(pg)
    with Session(runtime_pg) as db:
        def falhar(session):
            session.flush()
            raise RuntimeError('Falha ficticia antes do commit')
        event.listen(db,'before_commit',falhar)
        with pytest.raises((RuntimeError,FalhaPersistencia)):habilitar(db,s,p,uuid4())
    assert snapshot(pg)==antes
    with pg.connect() as c:assert c.scalar(text('SELECT count(*) FROM controles_financeiros_comanda'))==0


def test_habilitacao_libera_inclusao_e_fechamento_sem_reescrever_auditoria(pg,runtime_pg,portal):
    from app.services.itens_comanda import adicionar_servico
    from app.services.financeiro import fechar_comanda
    s=portal;p=body(runtime_pg,s);key=uuid4()
    with Session(runtime_pg) as db:
        r=habilitar(db,s,p,key)
        adicionar_servico(s['comanda'],servico_id=s['service'],quantidade=1,chave_idempotencia=uuid4(),db=db,usuario=ator(db,s))
        fechar_comanda(s['comanda'],pagamentos=[dict(valor=Decimal('60.50'),forma='pix',recebido_em=datetime.now(timezone.utc),confirmado=True)],chave_idempotencia=uuid4(),db=db,usuario=ator(db,s))
        assert resumo(db,s).situacao=='fechado'
        assert habilitar(db,s,p,key)==r  # Recuperacao original mesmo apos fechar.


def test_migracao_nao_amplia_permissoes_e_auditoria_imutavel(pg,runtime_pg,portal):
    from sqlalchemy.exc import DBAPIError
    p=body(runtime_pg,portal)
    with Session(runtime_pg) as db:habilitar(db,portal,p,uuid4())
    with runtime_pg.connect() as c:
        for role in ['anon','authenticated','service_role']:
            assert not c.scalar(text("SELECT has_any_column_privilege(:r,'public.controles_financeiros_comanda','SELECT,INSERT,UPDATE,REFERENCES')"),{'r':role})
        assert c.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.controles_financeiros_comanda'::regclass"))
    for sql in ["UPDATE controles_financeiros_comanda SET motivo='alterado'",'DELETE FROM controles_financeiros_comanda']:
        with pytest.raises(DBAPIError), pg.begin() as c:c.execute(text(sql))


def test_migracao_preserva_controle_preexistente(pg,portal):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from test_modelagem_filiais import scripts
    s=portal
    with pg.begin() as c:
        c.execute(text("INSERT INTO controles_financeiros_comanda(comanda_id,filial_id,registrado_por,motivo) VALUES(:comanda,:filial,:user,'Controle anterior')"),s)
        c.execute(text('ALTER TABLE controles_financeiros_comanda DROP CONSTRAINT ck_controle_idempotencia'))
        c.execute(text('ALTER TABLE controles_financeiros_comanda DROP COLUMN chave_idempotencia, DROP COLUMN fingerprint'))
        antes=c.scalar(text('SELECT to_jsonb(t) FROM controles_financeiros_comanda t'))
        with Operations.context(MigrationContext.configure(c)):
            scripts().get_revision('f05c82d931ae').module.upgrade()
        depois=c.scalar(text("SELECT to_jsonb(t)-'chave_idempotencia'-'fingerprint' FROM controles_financeiros_comanda t"))
        assert antes==depois
        assert c.scalar(text('SELECT chave_idempotencia IS NULL AND fingerprint IS NULL FROM controles_financeiros_comanda'))


def test_cancelamento_concorrente_impede_habilitacao(pg,runtime_pg,portal):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=portal;p=body(runtime_pg,s)
    def cancelar(db):
        db.execute(text("UPDATE agendamentos SET status='cancelado' WHERE id=:agendamento"),s)
        db.execute(text("UPDATE comandas SET status='cancelada' WHERE id=:comanda"),s)
        db.commit()
        return 'cancelada'
    um,dois=disputar(runtime_pg,cancelar,lambda db:habilitar(db,s,p,uuid4()))
    assert um=='cancelada' and isinstance(dois,EstadoFinanceiroIncompativel)
    with pg.connect() as c:assert c.scalar(text('SELECT count(*) FROM controles_financeiros_comanda'))==0


@pytest.mark.parametrize('situacao',['pendente','aguardando','em_atendimento'])
def test_habilita_sem_alterar_situacao_operacional(pg,runtime_pg,portal,situacao):
    with pg.begin() as c:
        c.execute(text('UPDATE agendamentos SET status=:status'),{'status':situacao})
        c.execute(text('UPDATE comandas SET status=:status'),{'status':'pendente' if situacao=='pendente' else 'aberta'})
    antes=snapshot(pg);p=body(runtime_pg,portal)
    with Session(runtime_pg) as db:habilitar(db,portal,p,uuid4())
    assert snapshot(pg)==antes


def test_consulta_http_conferencia_nao_muta_e_exige_sessao(api,pg,portal):
    antes=snapshot(pg)
    r=requisitar(api,portal)
    assert r[0]==200,r
    assert r[1]['habilitacao']['origem']=='portal_cliente'
    assert r[1]['habilitacao']['total']=='30.50'
    assert r[1]['habilitacao']['itens'][0]['preco']=='30.50'
    assert r[1]['situacao']=='nao_verificado' and r[1]['saldo'] is None
    assert requisitar(api,portal,token='')[0]==401
    assert snapshot(pg)==antes
    with pg.connect() as c:assert c.scalar(text('SELECT count(*) FROM controles_financeiros_comanda'))==0
