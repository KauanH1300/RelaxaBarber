"""Migracao, runtime restrito, rollback e concorrencia no PostgreSQL descartavel."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def entrega(monkeypatch):
    from app.services import entrega_codigo_cliente as smtp
    letters=[]
    monkeypatch.setattr(smtp,'configuracao',lambda:True)
    monkeypatch.setattr(smtp,'enviar',lambda email,code:letters.append((email,code)))
    return letters


def criar(engine,email,phone):
    from app.models import Cliente,ContaPortalCliente
    from app.core.security import hash_senha
    with Session(engine) as db,db.begin():
        c=Cliente(nome='Teste troca',email=email,telefone=phone,conta_ativada=True,senha_hash=hash_senha('Senha-teste-longa-123'))
        db.add(c);db.flush();db.add(ContaPortalCliente(cliente_id=c.id,email_confirmado=email))
        return c.id


def preparar(engine,letters,email,novo,ip):
    from app.services import troca_email_cliente as s
    from app.services import portal_cliente as portal
    from app.schemas.portal_cliente import TrocarEmailPortal,ConfirmarPortal,LoginPortal
    with Session(engine) as db:
        token=portal.login(db,LoginPortal(email=email,senha='Senha-teste-longa-123'),ip)
        pedido=s.solicitar(db,TrocarEmailPortal(email_novo=novo),ip,token)
        s.confirmar(db,ConfirmarPortal(solicitacao_id=pedido['solicitacao_id'],codigo=letters[-1][1]),ip,'atual',token)
    return ConfirmarPortal(solicitacao_id=pedido['solicitacao_id'],codigo=letters[-1][1]),token


def test_runtime_troca_recupera_e_preserva_id(runtime_pg,entrega):
    from app.services import troca_email_cliente as s,portal_cliente as portal
    from app.schemas.portal_cliente import ContatoPortal,RedefinirPortal,LoginPortal
    from app.models import Cliente,ContaPortalCliente
    id_=criar(runtime_pg,'atual@example.com','11911112222')
    pedido,sessao=preparar(runtime_pg,entrega,'atual@example.com','novo@example.com','127.0.0.1')
    with Session(runtime_pg) as db:
        token=portal.login(db,LoginPortal(email='atual@example.com',senha='Senha-teste-longa-123'),'127.0.0.1')
        s.confirmar(db,pedido,'127.0.0.1','novo',sessao)
        assert db.get(Cliente,id_).email==db.get(ContaPortalCliente,id_).email_confirmado=='novo@example.com'
        with pytest.raises(portal.PortalFalha):portal.autenticar(db,token)
        recovery=portal.solicitar(db,ContatoPortal(email='novo@example.com'),'127.0.0.1','recuperacao')
        portal.confirmar(db,RedefinirPortal(solicitacao_id=recovery['solicitacao_id'],codigo=entrega[-1][1],senha='Nova-senha-teste-123'),'127.0.0.1','recuperacao')
        assert portal.login(db,LoginPortal(email='novo@example.com',senha='Nova-senha-teste-123'),'127.0.0.1')
        with pytest.raises(portal.PortalFalha):portal.login(db,LoginPortal(email='atual@example.com',senha='Senha-teste-longa-123'),'127.0.0.1')


def test_constraint_impede_edicao_unilateral(runtime_pg,entrega):
    from app.models import Cliente,ContaPortalCliente
    id_=criar(runtime_pg,'atual@example.com','11911112222')
    with Session(runtime_pg) as db:
        with pytest.raises(IntegrityError):
            with db.begin():db.get(Cliente,id_).email='contorno@example.com'
        assert db.get(Cliente,id_).email=='atual@example.com'
        assert db.get(ContaPortalCliente,id_).email_confirmado=='atual@example.com'


def test_rollback_do_commit_preserva_identidade_e_pedido(runtime_pg,entrega,pg):
    from app.services import troca_email_cliente as s
    from app.models import Cliente,ContaPortalCliente
    from app.models.portal_cliente import TrocaEmailCliente
    from app.services.persistencia import FalhaPersistencia
    id_=criar(runtime_pg,'atual@example.com','11911112222')
    pedido,sessao=preparar(runtime_pg,entrega,'atual@example.com','novo@example.com','127.0.0.1')
    with pg.begin() as conn:
        conn.execute(text("""CREATE FUNCTION public.falha_homologacao() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'falha transacional injetada' USING ERRCODE='23514'; END $$"""))
        conn.execute(text('CREATE CONSTRAINT TRIGGER falha_troca AFTER UPDATE ON public.portal_clientes_contas DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.falha_homologacao()'))
    with Session(runtime_pg) as db:
        with pytest.raises(FalhaPersistencia):s.confirmar(db,pedido,'127.0.0.1','novo',sessao)
        db.rollback()
        assert db.get(Cliente,id_).email==db.get(ContaPortalCliente,id_).email_confirmado=='atual@example.com'
        assert not db.get(TrocaEmailCliente,pedido.solicitacao_id).consumido


def test_confirmacoes_concorrentes_para_mesmo_destino(runtime_pg,entrega):
    from app.services import troca_email_cliente as s,portal_cliente as portal
    from app.models import Cliente
    criar(runtime_pg,'um@example.com','11911112222');criar(runtime_pg,'dois@example.com','21911112222')
    a=preparar(runtime_pg,entrega,'um@example.com','novo@example.com','127.0.0.1')
    now=portal.agora()
    # Only the fixture clock advances, never production limits or database data.
    from unittest.mock import patch
    with patch.object(portal,'agora',lambda:now+timedelta(minutes=2)):
        b=preparar(runtime_pg,entrega,'dois@example.com','novo@example.com','127.0.0.2')
    barrier=Barrier(2,timeout=10)
    def confirm(item):
        pedido,sessao=item
        with Session(runtime_pg) as db:
            barrier.wait()
            try:s.confirmar(db,pedido,'127.0.0.3','novo',sessao);return 200
            except portal.PortalFalha as exc:return exc.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(confirm,[a,b]))==[200,400]
    with Session(runtime_pg) as db:
        assert db.query(Cliente).filter(Cliente.email=='novo@example.com').count()==1


def test_rls_acl_trocas(runtime_pg,pg):
    with pg.connect() as conn:
        table='public.portal_clientes_trocas_email'
        assert conn.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:t)'),{'t':table})
        for role in ('anon','authenticated','service_role'):
            assert not conn.scalar(text("SELECT has_any_column_privilege(:r,:t,'SELECT,INSERT,UPDATE')"),{'r':role,'t':table})
        assert not conn.scalar(text("SELECT has_table_privilege('relaxabarber_runtime',:t,'DELETE,TRUNCATE')"),{'t':table})
