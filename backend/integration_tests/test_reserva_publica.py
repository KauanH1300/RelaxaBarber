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
        db.execute(text("UPDATE filiais SET endereco='Rua de teste, 1', agenda_publica=true WHERE id=:id"), {'id': data['filial']})
        c=db.get(Cliente,data['client']);c.email='cliente@example.com';c.conta_ativada=True;c.senha_hash=hash_senha('Senha-ficticia-longa-123')
        db.add(ContaPortalCliente(cliente_id=c.id,email_confirmado=c.email))
        db.add_all([FilialHorario(filial_id=data['filial'],dia_semana=d,fechado=False,hora_inicio=time(8),hora_fim=time(18)) for d in range(7)])
        db.add_all([HabilitacaoServico(filial_id=data['filial'],barbeiro_id=data[k],servico_id=data['service']) for k in ('user','other')])
    with Session(runtime_pg) as db:
        token=login(db,LoginPortal(email='cliente@example.com',senha='Senha-ficticia-longa-123'),'127.0.0.1')
    return data|{'token':token,'engine':runtime_pg}


def test_multiplos_servicos_e_filial(agenda, pg):
    from app.models import Servico, AgendamentoServico, ItemComanda, Agendamento, Comanda
    from app.services.reserva_publica import confirmar, listar_profissionais, listar_horarios
    s=agenda
    with Session(pg) as db, db.begin():
        outro=Servico(nome='Barba ficticia',preco=20,tempo_estimado=30,comissao_padrao=10,ativo=True)
        db.add(outro); db.flush(); outro_id=outro.id
    pedido=payload(s,servico_id=None,servicos_ids=[s['service'],outro_id],filial_id=s['filial'])
    with Session(s['engine']) as db:
        assert len(listar_profissionais(db,[s['service'],outro_id],s['filial']))==2
        disponibilidade=listar_horarios(db,[s['service'],outro_id],date(2099,5,20),s['user'],s['filial'])
        assert disponibilidade['duracao']==60
        assert disponibilidade['horarios'] and set(disponibilidade['recomendados']) <= set(disponibilidade['horarios'])
        resultado=confirmar(db,pedido,s['token'])
    with Session(s['engine']) as db:
        a=db.get(Agendamento,resultado.id)
        assert len(a.servicos)==2
        c=db.scalar(select(Comanda).where(Comanda.agendamento_id==a.id))
        assert len(c.itens)==2 and c.valor_total==50
        assert db.query(AgendamentoServico).count()==2 and db.query(ItemComanda).count()==2


def test_filial_desabilitada_nao_fica_publica(agenda, pg):
    from app.models import Filial
    from app.services.reserva_publica import listar_filiais_publicas, listar_profissionais
    from app.services.portal_cliente import PortalFalha
    s=agenda
    with Session(pg) as db, db.begin():
        original=db.get(Filial,s['filial'])
        outra=Filial(nome='Filial privada',empresa_id=original.empresa_id,endereco='Rua privada',agenda_publica=False)
        db.add(outra); db.flush(); outra_id=outra.id
    with Session(s['engine']) as db:
        assert [f.id for f in listar_filiais_publicas(db)]==[s['filial']]
        with pytest.raises(PortalFalha): listar_profissionais(db,[s['service']],outra_id)


def test_varias_filiais_exigem_escolha(agenda, pg):
    from app.models import Filial
    from app.services.reserva_publica import listar_filiais_publicas, listar_profissionais
    from app.services.portal_cliente import PortalFalha
    s=agenda
    with Session(pg) as db, db.begin():
        original=db.get(Filial,s['filial'])
        outra=Filial(nome='Filial B',empresa_id=original.empresa_id,endereco='Rua B',agenda_publica=True)
        db.add(outra); db.flush(); outra_id=outra.id
    with Session(s['engine']) as db:
        assert {f.id for f in listar_filiais_publicas(db)}=={s['filial'],outra_id}
        with pytest.raises(PortalFalha): listar_profissionais(db,[s['service']])
        assert len(listar_profissionais(db,[s['service']],s['filial']))==2
        assert listar_profissionais(db,[s['service']],outra_id)==[]


def test_configuracao_publica_exige_admin(agenda, pg):
    from app.models import Usuario, PerfilEnum
    from app.schemas.filial import ConfiguracaoAgendaFilial
    from app.services.gestao_filiais import configurar_agenda_publica
    from app.services.errors import SemPermissao
    from pydantic import ValidationError
    s=agenda
    with pytest.raises(ValidationError): ConfiguracaoAgendaFilial(endereco=' ',agenda_publica=True)
    with Session(pg) as db, db.begin():
        admin=Usuario(nome='Admin QA',email='qa-publico-admin@example.test',senha_hash='ficticio',perfil=PerfilEnum.ADMIN)
        db.add(admin); db.flush(); admin_id=admin.id
    with Session(s['engine']) as db:
        with pytest.raises(SemPermissao):
            configurar_agenda_publica(db,db.get(Usuario,s['user']),s['filial'],ConfiguracaoAgendaFilial(endereco='Rua B',agenda_publica=True))
    with Session(s['engine']) as db:
        filial=configurar_agenda_publica(db,db.get(Usuario,admin_id),s['filial'],ConfiguracaoAgendaFilial(endereco='Rua B',agenda_publica=True))
        assert filial.endereco=='Rua B' and filial.agenda_publica


def test_profissional_precisa_aceitar_todos_servicos(agenda, pg):
    from app.models import Servico
    from app.models.reserva_portal import RestricaoServico
    from app.services.reserva_publica import listar_profissionais
    s=agenda
    with Session(pg) as db, db.begin():
        outro=Servico(nome='Outro serviço',preco=15,tempo_estimado=30,comissao_padrao=10,ativo=True)
        db.add(outro); db.flush(); outro_id=outro.id
        db.add(RestricaoServico(filial_id=s['filial'],barbeiro_id=s['user'],servico_id=outro_id))
    with Session(s['engine']) as db:
        assert [p.id for p in listar_profissionais(db,[s['service'],outro_id],s['filial'])]==[s['other']]


def test_multiplos_servicos_nao_sobrepoem_agendamento(agenda, pg):
    from app.models import Servico
    from app.services.reserva_publica import confirmar
    from app.services.errors import HorarioOcupado
    s=agenda
    with Session(pg) as db, db.begin():
        outro=Servico(nome='Serviço QA',preco=20,tempo_estimado=30,comissao_padrao=10,ativo=True)
        db.add(outro); db.flush(); outro_id=outro.id
    primeiro=payload(s,servico_id=None,servicos_ids=[s['service'],outro_id],filial_id=s['filial'])
    segundo=payload(s,hora_inicio=time(9,30))
    with Session(s['engine']) as db: confirmar(db,primeiro,s['token'])
    with Session(s['engine']) as db:
        with pytest.raises(HorarioOcupado): confirmar(db,segundo,s['token'])


def test_recomendacoes_nao_alteram_disponibilidade_e_sao_equivalentes(agenda, monkeypatch):
    from app.services import otimizacao_agenda as ot, reserva_publica, jornada
    s=agenda
    monkeypatch.setenv('AGENDAMENTO_OTIMIZACAO_ESTRATEGIA','sequencial')
    with Session(s['engine']) as db:
        referencia=jornada.horarios_disponiveis(db,s['filial'],s['user'],date(2099,5,20),30)
        sequencial=reserva_publica.listar_horarios(db,[s['service']],date(2099,5,20),s['user'],s['filial'])
    monkeypatch.setenv('AGENDAMENTO_OTIMIZACAO_ESTRATEGIA','paralelo')
    monkeypatch.setattr(ot,'MIN_CANDIDATOS_PARALELO',0)
    monkeypatch.setattr(ot,'MAX_PROCESSOS',2)
    with Session(s['engine']) as db:
        paralelo=reserva_publica.listar_horarios(db,[s['service']],date(2099,5,20),s['user'],s['filial'])
    assert sequencial==paralelo
    assert sequencial['horarios']==referencia['horarios']
    assert sequencial['horarios'] and set(sequencial['recomendados']) <= set(sequencial['horarios'])
    assert len(sequencial['recomendados'])==min(3,len(sequencial['horarios']))


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
        for tabela in ('habilitacoes_servicos','portal_clientes_reservas','restricoes_servicos'):
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


def test_restricoes_sao_revalidadas_apos_consulta_e_qualquer_atribui_outro(agenda):
    from app.services.reserva_publica import listar_profissionais,confirmar,configurar_restricoes
    from app.schemas.reserva_publica import RestricoesUpdate
    from app.models import Usuario,PerfilEnum
    from app.services.errors import HorarioOcupado
    s=agenda
    with Session(s['engine']) as db:assert len(listar_profissionais(db,s['service']))==2
    with Session(s['engine']) as db:
        admin=Usuario(nome='Admin',email='admin-restricao@example.com',senha_hash='ficticio',perfil=PerfilEnum.ADMIN)
        db.add(admin);db.commit()
        configurar_restricoes(db,admin,s['filial'],s['user'],RestricoesUpdate(servicos=[s['service']]))
    with Session(s['engine']) as db:
        with pytest.raises(HorarioOcupado):confirmar(db,payload(s),s['token'])
    with Session(s['engine']) as db:
        assert confirmar(db,payload(s,barbeiro_id=None),s['token']).barbeiro.id==s['other']
    contagens(s,1)


def test_migracao_aditiva_preserva_habilitacoes_e_reservas(agenda,pg):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from app.services.reserva_publica import confirmar
    from app.models.reserva_portal import HabilitacaoServico
    s=agenda
    with Session(s['engine']) as db:confirmar(db,payload(s),s['token'])
    with Session(pg) as db:legado=db.query(HabilitacaoServico).count()
    assert legado==2
    # Recreate exactly the additive step on this disposable DB, retaining all other tables/data.
    config=Config();config.set_main_option('script_location','alembic')
    revision=ScriptDirectory.from_config(config).get_revision('d83e60a719bc')
    with pg.begin() as conn:
        conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        conn.execute(text('DROP TABLE public.restricoes_servicos'))
        with Operations.context(MigrationContext.configure(conn)):revision.module.upgrade()
    with Session(s['engine']) as db:
        assert db.query(HabilitacaoServico).count()==legado
        assert db.scalar(text('SELECT count(*) FROM public.restricoes_servicos'))==0
    assert contagens(s,1)==1
