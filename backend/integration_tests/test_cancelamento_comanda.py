"""Cancelamento direto: PostgreSQL descartável, API real e locks concorrentes."""
from uuid import uuid4
from decimal import Decimal
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from test_financeiro_persistencia import data, legado, financeiro, pagar, estornar, fechar, criar_comanda
from test_financeiro_servicos import caso, ator, disputar
from test_financeiro_http import api, requisitar
from test_itens_comanda import incluir


@pytest.fixture
def vazia(pg, caso):
    with pg.begin() as c:
        c.execute(text("UPDATE comandas SET status='aberta',data_fechamento=NULL,valor_total=0 WHERE id=:comanda"), caso)
        c.execute(text('UPDATE itens_comanda SET ativo=false WHERE comanda_id=:comanda'), caso)
    return caso


def dados(**kw):
    from app.schemas.cancelamento_comanda import CancelamentoComandaCreate
    return CancelamentoComandaCreate(**({'versao':0,'motivo':'Cancelamento fictício conferido','confirmado':True}|kw))


def cancelar(db,s,key=None,perfil='recepcao',**kw):
    from app.services.cancelamento_comanda import cancelar as executar
    return executar(s['comanda'],dados(**kw),key or uuid4(),db,ator(db,s,perfil),s['filial'])


def registros(pg):
    with pg.connect() as c:
        return c.scalar(text('SELECT count(*) FROM cancelamentos_comanda'))


@pytest.mark.parametrize('perfil',['admin','recepcao','barbeiro','barbeiro_chefe'])
def test_http_permissoes_confirmacao_e_replay(api,pg,vazia,perfil):
    s=vazia;key=uuid4();body=dados().model_dump()
    if perfil=='barbeiro_chefe':
        with pg.begin() as c:c.execute(text("UPDATE usuarios SET perfil='BARBEIRO_CHEFE' WHERE id=:user"),s)
        s['atores'][perfil]=s['user']
    r=requisitar(api,s,'cancelamento',body=body,key=key,perfil=perfil)
    assert r[0]==(200 if perfil in ['admin','recepcao'] else 403),r
    assert registros(pg)==(1 if r[0]==200 else 0)
    if r[0]==200:
        assert r[1]['registrado_por']==str(s['atores'][perfil]) and r[1]['registrado_em'] and r[1]['versao']==1
        assert requisitar(api,s,'cancelamento',body=body,key=key,perfil=perfil)==r
        assert requisitar(api,s,'cancelamento',body=body|{'motivo':'Outro'},key=key,perfil=perfil)[0]==409


@pytest.mark.parametrize('modo',['outra_filial','vinculo_revogado','usuario_inativo'])
def test_escopo_e_revogacao_rechecados(api,pg,vazia,modo):
    s=vazia
    if modo!='outra_filial':
        with pg.begin() as c:
            q="UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id" if modo=='vinculo_revogado' else "UPDATE usuarios SET ativo=false WHERE id=:id"
            c.execute(text(q),{'id':s['atores']['recepcao']})
    r=requisitar(api,s,'cancelamento',body=dados().model_dump(),key=uuid4(),query=f"?filial_id={s['outra_filial']}" if modo=='outra_filial' else '')
    assert r[0] in [401,403,404],r
    assert registros(pg)==0


@pytest.mark.parametrize('alteracao',[{'motivo':' '},{'confirmado':False},{'versao':1},{'versao':True}])
def test_motivo_confirmacao_versao(api,pg,vazia,alteracao):
    r=requisitar(api,vazia,'cancelamento',body=dados().model_dump()|alteracao,key=uuid4())
    assert r[0] in [409,422],r
    assert registros(pg)==0


@pytest.mark.parametrize('estado',['pendente','aberta','fechada','cancelada'])
def test_estados_integridade_e_historico(runtime_pg,pg,vazia,estado):
    from app.models import Comanda
    from app.schemas.comanda import ComandaResponse
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=vazia
    with pg.begin() as c:
        c.execute(text('UPDATE comandas SET status=:status WHERE id=:comanda'),s|{'status':estado})
        before=c.scalar(text('SELECT to_jsonb(a) FROM agendamentos a WHERE id=:agendamento'),s)
        items=list(c.scalars(text('SELECT to_jsonb(i) FROM itens_comanda i WHERE comanda_id=:comanda'),s))
    with Session(runtime_pg) as db:
        if estado in ['fechada','cancelada']:
            with pytest.raises(EstadoFinanceiroIncompativel):cancelar(db,s)
        else:
            r=cancelar(db,s);assert r.status_anterior==estado
            dto=ComandaResponse.model_validate(db.get(Comanda,s['comanda']))
            assert dto.cancelamento==r and dto.itens==[] and dto.versao_itens==1
    with pg.connect() as c:
        assert c.scalar(text('SELECT to_jsonb(a) FROM agendamentos a WHERE id=:agendamento'),s)==before
        assert list(c.scalars(text('SELECT to_jsonb(i) FROM itens_comanda i WHERE comanda_id=:comanda'),s))==items


@pytest.mark.parametrize('movimento',['item_ativo','pagamento','estorno_integral','fechamento_zero','beneficio'])
def test_nao_confunde_vazia_ou_saldo_zero_com_ausencia_de_movimento(runtime_pg,pg,vazia,movimento):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=vazia
    with pg.begin() as c:
        if movimento=='item_ativo':c.execute(text('UPDATE itens_comanda SET ativo=true,preco_unitario=0 WHERE comanda_id=:comanda'),s)
        elif movimento in ['pagamento','estorno_integral']:
            p=pagar(c,s)
            if movimento=='estorno_integral':estornar(c,s,p['id'],valor=Decimal('10'))
        elif movimento=='fechamento_zero':fechar(c,s,total=Decimal('0'),liquido=Decimal('0'),motivo='Gratuidade anterior')
        else:
            c.execute(text("INSERT INTO beneficios_comanda(id,comanda_id,filial_id,registrado_por,motivo,chave_idempotencia,fingerprint,resultado) VALUES(:id,:comanda,:filial,:user,'Beneficio anterior',:key,:fp,'{}')"),s|{'id':uuid4(),'key':uuid4(),'fp':'a'*64})
    with Session(runtime_pg) as db,pytest.raises(EstadoFinanceiroIncompativel):cancelar(db,s)
    assert registros(pg)==0


def test_legado_sem_controle_nao_e_presumido_sem_movimento(runtime_pg,pg,vazia):
    from app.services.financeiro_errors import HistoricoFinanceiroNaoVerificado
    with pg.begin() as c:
        novo=criar_comanda(c,vazia,dia='2099-01-03')
        c.execute(text("UPDATE comandas SET status='aberta',data_fechamento=NULL WHERE id=:comanda"),novo)
        c.execute(text('UPDATE itens_comanda SET ativo=false WHERE comanda_id=:comanda'),novo)
    with Session(runtime_pg) as db,pytest.raises(HistoricoFinanceiroNaoVerificado):cancelar(db,vazia|{'comanda':novo['comanda']})


def test_habilitacao_financeira_posterior_impede_cancelamento(runtime_pg,pg,vazia):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with pg.begin() as c:
        novo=criar_comanda(c,vazia,dia='2099-01-04')
        c.execute(text("UPDATE comandas SET status='aberta',data_fechamento=NULL WHERE id=:comanda"),novo)
        c.execute(text('UPDATE itens_comanda SET ativo=false WHERE comanda_id=:comanda'),novo)
        c.execute(text("INSERT INTO controles_financeiros_comanda(comanda_id,filial_id,registrado_por,motivo,chave_idempotencia,fingerprint) VALUES(:comanda,:filial,:user,'Habilitação conferida',:key,:fp)"),novo|{'key':uuid4(),'fp':'a'*64})
    with Session(runtime_pg) as db,pytest.raises(EstadoFinanceiroIncompativel):cancelar(db,vazia|{'comanda':novo['comanda']})


def test_comanda_sem_linhas_tambem_pode_cancelar(runtime_pg,pg,vazia):
    # Preparação exclusiva do banco descartável: nenhuma linha preexistente
    # é removida pelo serviço de cancelamento.
    with pg.begin() as c:c.execute(text('DELETE FROM itens_comanda WHERE comanda_id=:comanda'),vazia)
    with Session(runtime_pg) as db:assert cancelar(db,vazia).status=='cancelada'


@pytest.mark.parametrize('modo',['replay','duas_chaves','inclusao_primeiro','cancelamento_primeiro'])
def test_concorrencia_real(runtime_pg,pg,vazia,modo):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s=vazia;key=uuid4()
    if modo=='inclusao_primeiro':
        a,b=disputar(runtime_pg,lambda db:incluir(db,s),lambda db:cancelar(db,s))
        assert isinstance(b,EstadoFinanceiroIncompativel) and registros(pg)==0
    elif modo=='cancelamento_primeiro':
        a,b=disputar(runtime_pg,lambda db:cancelar(db,s),lambda db:incluir(db,s))
        assert isinstance(b,EstadoFinanceiroIncompativel) and registros(pg)==1
    else:
        a,b=disputar(runtime_pg,lambda db:cancelar(db,s,key),lambda db:cancelar(db,s,key if modo=='replay' else uuid4()))
        assert (a==b if modo=='replay' else isinstance(b,EstadoFinanceiroIncompativel))
        assert registros(pg)==1


def test_cancelada_bloqueia_operacoes_financeiras_e_servicos(api,pg,vazia):
    with Session(pg) as db:cancelar(db,vazia)
    for suffix,body in [('itens/servicos',{'servico_id':str(vazia['service']),'quantidade':1}),
        ('recebimentos',{'pagamentos':[{'valor':'1.00','forma':'dinheiro','confirmado':True,'recebido_em':'2026-01-01T12:00:00Z'}]}),
        ('beneficios/previa',{'acao':'comanda','versao':1,'motivo':'Depois','desconto_tipo':'percentual','desconto_valor':'10'}),
        ('fechamento-financeiro',{'motivo':'Depois','pagamentos':[]})]:
        assert requisitar(api,vazia,suffix,body=body,key=uuid4())[0]==409


def test_agendamento_pode_ser_cancelado_depois_sem_perder_auditoria(runtime_pg,pg,vazia):
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    s=vazia
    with pg.begin() as c:c.execute(text("UPDATE agendamentos SET status='aguardando' WHERE id=:agendamento"),s)
    with Session(runtime_pg) as db:
        r=cancelar(db,s)
        atualizar_status(s['agendamento'],AgendamentoStatusUpdate(status='cancelado',motivo_cancelamento='Reserva cancelada depois'),db,ator(db,s),s['filial'])
        assert cancelar(db,s,r.chave_idempotencia)==r
    assert registros(pg)==1


def test_cancelamento_de_agendamento_existente_preservado(runtime_pg,pg,vazia):
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    from app.services.comandas import buscar_detalhe
    s=vazia
    with pg.begin() as c:
        c.execute(text("UPDATE agendamentos SET status='aguardando' WHERE id=:agendamento"),s)
        c.execute(text('UPDATE itens_comanda SET ativo=true WHERE comanda_id=:comanda'),s)
    with Session(runtime_pg) as db:
        atualizar_status(s['agendamento'],AgendamentoStatusUpdate(status='cancelado',motivo_cancelamento='Fluxo existente'),db,ator(db,s),s['filial'])
        detalhe=buscar_detalhe(db,ator(db,s),s['comanda'],s['filial'])
        assert detalhe.status=='cancelada' and detalhe.atendimento.status=='cancelado'
        assert len(detalhe.itens)==1 and detalhe.cancelamento is None
    assert registros(pg)==0


def test_migracao_auditoria_imutavel_e_acl(runtime_pg,pg,vazia):
    with Session(runtime_pg) as db:cancelar(db,vazia)
    for engine in [pg,runtime_pg]:
        for q in ['UPDATE cancelamentos_comanda SET motivo=\'outro\'','DELETE FROM cancelamentos_comanda','TRUNCATE cancelamentos_comanda']:
            with pytest.raises(DBAPIError),engine.begin() as c:c.execute(text(q))
    with pg.connect() as c:
        assert not c.scalar(text("SELECT has_table_privilege('anon','cancelamentos_comanda','SELECT')"))
        assert not c.scalar(text("SELECT has_table_privilege('service_role','cancelamentos_comanda','INSERT')"))
        assert c.scalar(text("SELECT registrado_em=(resultado->>'registrado_em')::timestamptz FROM cancelamentos_comanda")) is True
