from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date,time
import pytest
from sqlalchemy import select,text,event
from sqlalchemy.orm import Session
from test_concorrencia import data  # noqa:F401
from test_reserva_publica import agenda,payload  # noqa:F401


@pytest.fixture
def minha(agenda):
    from app.services.reserva_publica import confirmar
    from app.services.minha_agenda import consultar
    s=agenda
    with Session(s['engine']) as db:
        id_=confirmar(db,payload(s),s['token']).id
        versao=consultar(db,s['token'],id_).atualizado_em
    return s|{'id':id_,'versao':versao}


def pedido(s,**changes):
    from app.schemas.minha_agenda import RemarcarCliente
    return RemarcarCliente(**(dict(data=date(2099,5,21),hora_inicio=time(10),barbeiro_id=s['other'],atualizado_em_esperado=s['versao'])|changes))


def test_remarcacao_mesma_comanda_autoria_e_financeiro_preservados(minha):
    from app.models import Agendamento,Comanda,Reagendamento
    from app.services.minha_agenda import remarcar
    s=minha
    with Session(s['engine']) as db:
        c=db.scalar(select(Comanda));antes=(c.id,c.agendamento_id,c.cliente_id,c.valor_total,len(c.itens))
        out=remarcar(db,s['token'],s['id'],pedido(s))
        db.expire_all();c=db.scalar(select(Comanda))
        assert (c.id,c.agendamento_id,c.cliente_id,c.valor_total,len(c.itens))==antes
        assert c.barbeiro_id==out.barbeiro.id==s['other']
        h=db.scalar(select(Reagendamento));assert h.registrado_por is None and h.registrado_por_cliente==s['client']
        assert db.get(Agendamento,s['id']).cliente_id==s['client']


@pytest.mark.parametrize('modo',['cancelamento','cancelamento_sem_preferencia','duas_remarcacoes','nova_reserva'])
def test_concorrencia_preserva_reserva_e_exclusao(minha,modo):
    from app.services.minha_agenda import remarcar,cancelar,consultar
    from app.services.reserva_publica import confirmar
    from app.schemas.minha_agenda import OperacaoAgendaCliente
    from app.services.errors import ConflitoEstadoAgendamento,HorarioOcupado
    from app.services.persistencia import ConflitoPersistencia
    from app.models import Agendamento,Comanda,Reagendamento
    s=minha;barrier=Barrier(2,timeout=10);segundo=None
    if modo=='duas_remarcacoes':
        with Session(s['engine']) as db:
            id_=confirmar(db,payload(s,hora_inicio=time(11)),s['token']).id
            segundo=(id_,consultar(db,s['token'],id_).atualizado_em)
    def executar(n):
        with Session(s['engine']) as db:
            db.execute(text("SET LOCAL statement_timeout='20s'"));barrier.wait()
            try:
                if n==0:
                    alvo = None if modo == 'cancelamento_sem_preferencia' else s['other']
                    remarcar(db,s['token'],s['id'],pedido(s,barbeiro_id=alvo))
                elif modo in ('cancelamento', 'cancelamento_sem_preferencia'):
                    cancelar(db,s['token'],s['id'],OperacaoAgendaCliente(atualizado_em_esperado=s['versao']))
                elif modo=='duas_remarcacoes':remarcar(db,s['token'],segundo[0],pedido(s,atualizado_em_esperado=segundo[1]))
                else:confirmar(db,payload(s,data=date(2099,5,21),hora_inicio=time(10),barbeiro_id=s['other']),s['token'])
                return 'ok'
            except (ConflitoEstadoAgendamento,HorarioOcupado,ConflitoPersistencia):return 'conflito'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(executar,[0,1]))==['conflito','ok']
    with Session(s['engine']) as db:
        assert db.query(Agendamento).count()==db.query(Comanda).count()
        assert db.query(Reagendamento).count()<=1
        assert db.query(Agendamento).filter(Agendamento.data==date(2099,5,21)).count()<=1


def test_rollback_nao_altera_reserva_comanda_nem_historico(minha):
    from app.services.minha_agenda import remarcar
    from app.models import Agendamento,Comanda,Reagendamento
    s=minha
    with Session(s['engine']) as db:
        def falhar(session):raise RuntimeError('falha injetada')
        event.listen(db,'before_commit',falhar)
        with pytest.raises(RuntimeError):remarcar(db,s['token'],s['id'],pedido(s))
    with Session(s['engine']) as db:
        assert db.get(Agendamento,s['id']).data==date(2099,5,20)
        assert db.scalar(select(Comanda.barbeiro_id))==s['user'] and db.query(Reagendamento).count()==0


def test_constraints_autoria_permissoes_e_historico_imutavel(minha,pg):
    from app.services.minha_agenda import remarcar
    from app.models import Reagendamento
    from sqlalchemy.exc import DBAPIError
    s=minha
    with Session(s['engine']) as db:remarcar(db,s['token'],s['id'],pedido(s))
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid='public.reagendamentos'::regclass"))
        assert conn.scalar(text("SELECT count(*) FROM pg_constraint WHERE conname IN ('ck_reagendamento_autor','ck_agendamento_autor_cancelamento','fk_reagendamento_cliente_autor','fk_agendamento_cliente_cancelamento') AND convalidated"))==4
        for role in ('anon','authenticated','service_role'):
            assert not conn.scalar(text("SELECT has_column_privilege(:r,'public.reagendamentos','registrado_por_cliente','SELECT')"),{'r':role})
    with Session(s['engine']) as db:
        with pytest.raises(DBAPIError):
            db.execute(text('DELETE FROM public.reagendamentos'));db.commit()
    with Session(pg) as db:
        h=db.scalar(select(Reagendamento))
        assert h.registrado_por_cliente==s['client']


def test_migracao_preserva_autoria_antiga(minha,pg):
    from app.services.reagendamento import aplicar_reagendamento
    from app.schemas.reagendamento import ReagendamentoUpdate
    from app.models import Agendamento
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    s=minha
    with Session(s['engine']) as db,db.begin():
        a=db.get(Agendamento,s['id'])
        aplicar_reagendamento(db,a,ReagendamentoUpdate(data=date(2099,5,21),hora_inicio=time(10),barbeiro_id=s['user'],atualizado_em_esperado=s['versao']),registrado_por=s['user'])
    with pg.begin() as conn:
        antes=conn.scalar(text("SELECT md5(string_agg((to_jsonb(r)-'registrado_por_cliente')::text,'' ORDER BY id)) FROM public.reagendamentos r"))
        conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        conn.execute(text('ALTER TABLE public.agendamentos DROP COLUMN cancelado_por_cliente'))
        conn.execute(text('ALTER TABLE public.reagendamentos DROP COLUMN registrado_por_cliente'))
        conn.execute(text('ALTER TABLE public.reagendamentos ALTER COLUMN registrado_por SET NOT NULL'))
        cfg=Config();cfg.set_main_option('script_location','alembic')
        with Operations.context(MigrationContext.configure(conn)):
            ScriptDirectory.from_config(cfg).get_revision('e94f71b820cd').module.upgrade()
        depois=conn.scalar(text("SELECT md5(string_agg((to_jsonb(r)-'registrado_por_cliente')::text,'' ORDER BY id)) FROM public.reagendamentos r"))
        assert antes==depois
