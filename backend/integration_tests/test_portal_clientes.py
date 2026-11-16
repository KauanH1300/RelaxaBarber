"""Ativação concorrente e permissões somente no PostgreSQL descartável."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID
import pytest
from sqlalchemy import select,text
from sqlalchemy.orm import Session


@pytest.fixture
def pedidos(runtime_pg,monkeypatch):
    from app.services import portal_cliente as service, entrega_codigo_cliente as entrega
    from app.schemas.portal_cliente import CadastroPortal
    cartas=[]
    monkeypatch.setattr(entrega,'configuracao',lambda:True)
    monkeypatch.setattr(entrega,'enviar',lambda email,codigo:cartas.append(codigo))
    dados=CadastroPortal(nome='Cliente teste',telefone='11999991234',email='portal@example.com',senha='Senha-ficticia-portal-123')
    with Session(runtime_pg) as db:
        um=service.solicitar(db,dados,'127.0.0.1','cadastro')
    now=service.agora();monkeypatch.setattr(service,'agora',lambda:now+timedelta(minutes=2))
    with Session(runtime_pg) as db:dois=service.solicitar(db,dados,'127.0.0.1','cadastro')
    return [(um['solicitacao_id'],cartas[0]),(dois['solicitacao_id'],cartas[1])]


@pytest.mark.parametrize('mesmo_codigo',[True,False])
def test_confirmacoes_atomicas_sem_duplicacao(runtime_pg,pedidos,mesmo_codigo):
    from app.services import portal_cliente as service
    from app.schemas.portal_cliente import ConfirmarPortal
    from app.models import Cliente,ContaPortalCliente
    barreira=Barrier(2,timeout=5)
    def confirmar(item):
        index,pedido=item
        with Session(runtime_pg) as db:
            db.execute(text("SET LOCAL statement_timeout='12s'"))
            barreira.wait()
            try:
                service.confirmar(db,ConfirmarPortal(solicitacao_id=pedido[0],codigo=pedido[1]),f'127.0.0.{index+1}','cadastro')
                return 200
            except service.PortalFalha as exc:return exc.status
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(confirmar,enumerate([pedidos[0],pedidos[0] if mesmo_codigo else pedidos[1]])))==[200,400]
    with Session(runtime_pg) as db:
        assert db.query(ContaPortalCliente).count()==1
        assert db.query(Cliente).filter(Cliente.email=='portal@example.com').count()==1


def test_acl_privado_e_sessao_revogada(runtime_pg,pedidos,pg):
    from app.services import portal_cliente as service
    from app.schemas.portal_cliente import ConfirmarPortal,LoginPortal
    from app.models import DesafioPortalCliente
    with Session(runtime_pg) as db:
        service.confirmar(db,ConfirmarPortal(solicitacao_id=pedidos[0][0],codigo=pedidos[0][1]),'127.0.0.1','cadastro')
        token=service.login(db,LoginPortal(email='portal@example.com',senha='Senha-ficticia-portal-123'),'127.0.0.1')
        assert service.autenticar(db,token).email=='portal@example.com'
        assert db.get(DesafioPortalCliente,pedidos[0][0]).dados is None
        service.logout(db,token)
        with pytest.raises(service.PortalFalha):service.autenticar(db,token)
    with pg.connect() as conn:
        for tabela in ('contas','desafios','limites','sessoes'):
            alvo='public.portal_clientes_'+tabela
            for role in ('anon','authenticated','service_role'):
                assert not conn.scalar(text('SELECT has_any_column_privilege(:role,:table,\'SELECT\')'),{'role':role,'table':alvo})
            assert conn.scalar(text('SELECT relrowsecurity FROM pg_class WHERE oid=to_regclass(:table)'),{'table':alvo})
