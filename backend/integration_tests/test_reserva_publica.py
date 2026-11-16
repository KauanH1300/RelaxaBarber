from concurrent.futures import ThreadPoolExecutor
from datetime import date,time
from threading import Barrier
from uuid import uuid4
import pytest
from sqlalchemy import select,text,event
from sqlalchemy.orm import Session
from test_concorrencia import data  # noqa:F401


@pytest.fixture
def agenda(runtime_pg,data,pg,monkeypatch):
    from app.models import Cliente,ContaPortalCliente,FilialHorario
    from app.models.reserva_portal import HabilitacaoServico
    from app.core.security import hash_senha
    from app.services.portal_cliente import login
    from app.schemas.portal_cliente import LoginPortal
    monkeypatch.delenv('PUBLIC_BOOKING_FILIAL_ID',raising=False)
    with Session(pg) as db,db.begin():
        c=db.get(Cliente,data['client']);c.email='cliente@example.com';c.conta_ativada=True;c.senha_hash=hash_senha('Senha-ficticia-longa-123')
        db.add(ContaPortalCliente(cliente_id=c.id,email_confirmado=c.email))
        db.add_all([FilialHorario(filial_id=data['filial'],dia_semana=d,fechado=False,hora_inicio=time(8),hora_fim=time(18)) for d in range(7)])
        db.add_all([HabilitacaoServico(filial_id=data['filial'],barbeiro_id=data[k],servico_id=data['service']) for k in ('user','other')])
    with Session(runtime_pg) as db:
        token=login(db,LoginPortal(email='cliente@example.com',senha='Senha-ficticia-longa-123'),'127.0.0.1')
    return data|{'token':token,'engine':runtime_pg}


def payload(s,**changes):
    from app.schemas.reserva_publica import ReservaPublicaCreate
    return ReservaPublicaCreate(**(dict(servico_id=s['service'],barbeiro_id=s['user'],data=date(2099,5,20),hora_inicio=time(9),chave=uuid4())|changes))


def contagens(s,total):
    from app.models import Agendamento,Comanda,AgendamentoServico,ItemComanda
    from app.models.reserva_portal import ReservaPortal
    with Session(s['engine']) as db:
        for model in (Agendamento,Comanda,AgendamentoServico,ItemComanda):assert db.query(model).count()==total
        return db.query(ReservaPortal).count()


@pytest.mark.parametrize('modo',['especifico','qualquer','idempotente'])
def test_confirmacoes_concorrentes_nao_duplicam_e_atribuem_profissional(agenda,modo):
    from app.services.reserva_publica import confirmar
    from app.services.errors import HorarioOcupado
    s=agenda;barrier=Barrier(2,timeout=10)
    um=payload(s,barbeiro_id=None if modo=='qualquer' else s['user'])
    dois=um if modo=='idempotente' else payload(s,barbeiro_id=None if modo=='qualquer' else s['user'])
    def reservar(dados):
        with Session(s['engine']) as db:
            db.execute(text("SET LOCAL statement_timeout='15s'"))
            barrier.wait()
            try:return confirmar(db,dados,s['token']).id
            except HorarioOcupado:return 'ocupado'
    with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(reservar,[um,dois]))
    if modo=='especifico':assert result.count('ocupado')==1;contagens(s,1)
    if modo=='qualquer':assert 'ocupado' not in result and result[0]!=result[1];contagens(s,2)
    if modo=='idempotente':assert result[0]==result[1] and contagens(s,1)==1


def test_portal_concorre_com_recepcao_pelas_mesmas_regras(agenda):
    from app.services.reserva_publica import confirmar
    from app.services.agendamento import criar_agendamento
    from app.services.errors import HorarioOcupado
    from app.services.persistencia import ConflitoPersistencia
    from app.schemas.agendamento import AgendamentoCreate
    from app.models import Usuario
    s=agenda;barrier=Barrier(2,timeout=10)
    def reservar(publico):
        with Session(s['engine']) as db:
            db.execute(text("SET LOCAL statement_timeout='15s'"));barrier.wait()
            try:
                if publico:confirmar(db,payload(s),s['token'])
                else:criar_agendamento(AgendamentoCreate(cliente_id=s['client'],filial_id=s['filial'],barbeiro_id=s['user'],data=date(2099,5,20),hora_inicio=time(9),servicos=[{'servico_id':s['service']}]),db,db.get(Usuario,s['user']))
                return 'ok'
            except (HorarioOcupado,ConflitoPersistencia):return 'ocupado'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(reservar,[True,False]))==['ocupado','ok']
    contagens(s,1)


def test_rollback_financeiro_e_pedido_atomicos(agenda):
    from app.services.reserva_publica import confirmar
    s=agenda
    with Session(s['engine']) as db:
        def falhar(session):raise RuntimeError('falha injetada')
        event.listen(db,'before_commit',falhar)
        with pytest.raises(RuntimeError):confirmar(db,payload(s),s['token'])
    assert contagens(s,0)==0


def test_migracao_rls_e_grants_minimos(agenda,pg):
    with pg.connect() as conn:
        for tabela in ('habilitacoes_servicos','portal_clientes_reservas'):
            assert conn.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:t)'),{'t':'public.'+tabela})
            for role in ('anon','authenticated','service_role'):
                assert not conn.scalar(text("SELECT has_any_column_privilege(:r,:t,'SELECT,INSERT,UPDATE')"),{'r':role,'t':'public.'+tabela})
        assert not conn.scalar(text("SELECT has_table_privilege('relaxabarber_runtime','public.portal_clientes_reservas','UPDATE,DELETE,TRUNCATE')"))


def test_horario_ocupado_entre_consulta_e_confirmacao(agenda):
    from app.services.reserva_publica import listar_horarios,confirmar
    from app.services.errors import HorarioOcupado
    s=agenda
    with Session(s['engine']) as db:assert '09:00' in listar_horarios(db,s['service'],date(2099,5,20),s['user'])['horarios']
    with Session(s['engine']) as db:confirmar(db,payload(s),s['token'])
    with Session(s['engine']) as db:
        with pytest.raises(HorarioOcupado):confirmar(db,payload(s),s['token'])
    contagens(s,1)
