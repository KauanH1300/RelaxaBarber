from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select, event
from test_portal_clientes import portal, ativar, cadastro, call as raw_call, logar  # noqa: F401


def call(p, endpoint, body=None, **kwargs):
    return raw_call(p, endpoint, body, **({'cookie':getattr(p,'token',None)} | kwargs))


def iniciar(p, novo='novo@example.com'):
    if not getattr(p,'token',None): p.token=logar(p,cadastro())
    status, pedido, _ = call(p, 'troca-email', {'email_novo':novo})
    assert status == 202
    return dict(solicitacao_id=pedido['solicitacao_id'], codigo=p.cartas[-1][1])


def atual(p, pedido):
    assert call(p, 'troca-email/confirmar-atual', pedido)[0] == 200
    return pedido | {'codigo':p.cartas[-1][1]}


def test_sucesso_preserva_id_revoga_sessoes_e_pedidos(portal):
    from app.models import Cliente, ContaPortalCliente, DesafioPortalCliente, SessaoPortalCliente
    from app.models.portal_cliente import TrocaEmailCliente
    p=portal; ativar(p); cookie=logar(p,cadastro())
    cliente=p.db.scalar(select(Cliente)); id_=cliente.id; senha=cliente.senha_hash; telefone=cliente.telefone
    # A pending recovery for the old identity must become unusable.
    from app.services import portal_cliente as s
    from uuid import uuid4
    pendente=DesafioPortalCliente(id=uuid4(), finalidade='recuperacao', codigo_hash='x'*64,
        email=cliente.email, cliente_id=id_, dados={'versao':1}, expira_em=s.agora()+timedelta(minutes=10))
    p.db.add(pendente); p.db.commit()
    pedido=iniciar(p); assert p.cartas[-1][0]=='cliente@example.com'
    assert call(p,'troca-email/confirmar-novo',pedido)[0]==400
    novo=atual(p,pedido); assert p.cartas[-1][0]=='novo@example.com'
    assert call(p,'troca-email/confirmar-atual',pedido)[0]==400
    assert call(p,'troca-email/confirmar-novo',novo)[0]==200
    p.db.refresh(cliente); conta=p.db.get(ContaPortalCliente,id_); p.db.refresh(pendente)
    assert cliente.id==id_ and cliente.email==conta.email_confirmado=='novo@example.com'
    assert cliente.telefone==telefone and cliente.senha_hash==senha and conta.versao==2
    assert p.db.query(Cliente).count()==1 and p.db.query(SessaoPortalCliente).count()==0
    assert pendente.consumido and pendente.dados is None
    assert all(item.consumido for item in p.db.scalars(select(TrocaEmailCliente)))
    assert call(p,'me',method='GET',cookie=cookie)[0]==401
    assert call(p,'login',{'email':cadastro()['email'],'senha':cadastro()['senha']})[0]==401
    assert logar(p,cadastro(email='novo@example.com'))
    assert call(p,'troca-email/confirmar-novo',novo)[0]==401


@pytest.mark.parametrize('etapa',['atual','novo'])
@pytest.mark.parametrize('caso',['invalido','expirado','limite'])
def test_codigos_e_limites(portal,etapa,caso):
    from app.models import Cliente
    from app.models.portal_cliente import TrocaEmailCliente
    from app.services import portal_cliente as s
    p=portal; ativar(p); pedido=iniciar(p)
    if etapa=='novo': pedido=atual(p,pedido)
    item=p.db.get(TrocaEmailCliente,UUID(pedido['solicitacao_id']))
    if caso=='expirado': item.expira_em=s.agora()-timedelta(seconds=1); p.db.commit()
    errado=pedido | {'codigo':'000000' if pedido['codigo']!='000000' else '111111'}
    for _ in range(5 if caso=='limite' else 1):
        assert call(p,'troca-email/confirmar-'+etapa,pedido if caso=='expirado' else errado)[0]==400
    if caso in ('limite','expirado'):
        assert call(p,'troca-email/confirmar-'+etapa,pedido)[0]==400
    assert p.db.scalar(select(Cliente)).email=='cliente@example.com'


@pytest.mark.parametrize('momento',['antes','depois'])
def test_email_duplicado_inclusive_apos_primeira_confirmacao(portal,momento):
    from app.models import Cliente
    p=portal; ativar(p); pedido=iniciar(p)
    if momento=='depois': pedido=atual(p,pedido)
    p.db.add(Cliente(nome='Outro cliente',email='NOVO@example.com',telefone='21999998888'));p.db.commit()
    assert call(p,'troca-email/confirmar-'+('atual' if momento=='antes' else 'novo'),pedido)[0]==400
    assert p.db.scalar(select(Cliente).where(Cliente.email=='cliente@example.com'))


def test_falha_transacional_nao_atualiza_metade_da_identidade(portal):
    from app.models import Cliente, ContaPortalCliente
    from app.models.portal_cliente import TrocaEmailCliente
    from app.services import troca_email_cliente as s
    from app.schemas.portal_cliente import ConfirmarPortal
    p=portal; ativar(p); pedido=atual(p,iniciar(p)); cliente=p.db.scalar(select(Cliente)); id_=cliente.id
    p.db.rollback()
    def falhar(session):
        raise RuntimeError('falha injetada antes do commit')
    event.listen(p.db,'before_commit',falhar)
    try:
        with pytest.raises(RuntimeError):
            s.confirmar(p.db,ConfirmarPortal(**pedido),'127.0.0.1','novo',p.token)
    finally: event.remove(p.db,'before_commit',falhar)
    p.db.rollback();p.db.expire_all()
    assert p.db.get(Cliente,id_).email==p.db.get(ContaPortalCliente,id_).email_confirmado=='cliente@example.com'
    assert not p.db.get(TrocaEmailCliente,UUID(pedido['solicitacao_id'])).consumido


def test_sem_sessao_e_origem_nao_autorizada_nao_enviam_codigo(portal):
    p=portal
    dados={'email_novo':'novo@example.com'}
    assert call(p,'troca-email',dados,origin='https://hostil.example')[0]==403
    assert call(p,'troca-email',dados)[0]==401
    assert not p.cartas


def test_falha_smtp_nao_deixa_codigo_utilizavel(portal,monkeypatch):
    from app.services import entrega_codigo_cliente as entrega
    from app.models.portal_cliente import TrocaEmailCliente
    p=portal; ativar(p); pedido=iniciar(p)
    def falhar(*args): raise entrega.EntregaIndisponivel()
    monkeypatch.setattr(entrega,'enviar',falhar)
    assert call(p,'troca-email/confirmar-atual',pedido)[0]==503
    assert p.db.get(TrocaEmailCliente,UUID(pedido['solicitacao_id'])).consumido


def test_limite_solicitacao_nao_reenvia_codigo(portal):
    p=portal; ativar(p); iniciar(p); total=len(p.cartas)
    iniciar(p)
    assert len(p.cartas)==total


def test_edicao_administrativa_nao_contorna_confirmacao(portal,monkeypatch):
    from app.api.routes import clientes as routes
    from app.schemas.cliente import ClienteUpdate
    from app.models import Cliente
    from fastapi import HTTPException
    from types import SimpleNamespace
    p=portal; ativar(p); cliente=p.db.scalar(select(Cliente)); id_=cliente.id;p.db.rollback()
    monkeypatch.setattr(routes,'_resolver_filial',lambda *a,**kw:SimpleNamespace(id='filial'))
    monkeypatch.setattr(routes.clientes_service,'consulta_local',lambda db,filial:db.query(Cliente))
    with pytest.raises(HTTPException) as exc:
        routes.editar_cliente(id_,ClienteUpdate(email='outro@example.com'),db=p.db,usuario=SimpleNamespace())
    assert exc.value.status_code==409
    assert p.db.get(Cliente,id_).email=='cliente@example.com'


@pytest.mark.parametrize('etapa',['pedido','atual','novo'])
@pytest.mark.parametrize('caso',['ausente','expirada','revogada','antiga','funcionario'])
def test_todas_etapas_exigem_sessao_cliente_recente(portal,etapa,caso):
    from app.models import SessaoPortalCliente
    from app.services import portal_cliente as s
    from app.core.security import criar_token
    from uuid import uuid4
    p=portal;ativar(p);pedido=iniciar(p)
    if etapa=='novo':pedido=atual(p,pedido)
    sessao=p.db.scalar(select(SessaoPortalCliente).where(SessaoPortalCliente.token_hash==s.segredo('sessao',p.token)))
    token=p.token
    if caso=='ausente':token=None
    if caso=='expirada':sessao.expira_em=s.agora()-timedelta(seconds=1)
    if caso=='antiga':sessao.expira_em=s.agora()+timedelta(hours=8,minutes=-11)
    if caso=='revogada':p.db.delete(sessao)
    if caso=='funcionario':token=criar_token(uuid4())
    p.db.commit();cartas=len(p.cartas)
    endpoint='troca-email' if etapa=='pedido' else 'troca-email/confirmar-'+etapa
    body={'email_novo':'outro@example.com'} if etapa=='pedido' else pedido
    assert call(p,endpoint,body,cookie=token)[0]==(403 if caso=='antiga' else 401)
    assert len(p.cartas)==cartas


@pytest.mark.parametrize('etapa',['atual','novo'])
def test_outro_cliente_nao_confirma_nem_consume_tentativas(portal,etapa):
    from app.models import Cliente,ContaPortalCliente
    from app.models.portal_cliente import TrocaEmailCliente
    from app.core.security import hash_senha
    p=portal;ativar(p);pedido=iniciar(p)
    if etapa=='novo':pedido=atual(p,pedido)
    c=Cliente(nome='Outra conta',email='outro@example.com',telefone='21988887777',conta_ativada=True,senha_hash=hash_senha(cadastro()['senha']))
    p.db.add(c);p.db.flush();p.db.add(ContaPortalCliente(cliente_id=c.id,email_confirmado=c.email));p.db.commit()
    token=logar(p,cadastro(email=c.email))
    item=p.db.get(TrocaEmailCliente,UUID(pedido['solicitacao_id']));antes=item.tentativas
    assert call(p,'troca-email/confirmar-'+etapa,pedido,cookie=token)[0]==400
    p.db.refresh(item);assert item.tentativas==antes and not item.consumido


def test_email_atual_nao_pode_ser_forjado_no_pedido(portal):
    p=portal;ativar(p);p.token=logar(p,cadastro());antes=len(p.cartas)
    assert call(p,'troca-email',{'email':'outro@example.com','email_novo':'novo@example.com'})[0]==422
    assert len(p.cartas)==antes


def test_login_renovado_permite_retomar_sem_reenviar_codigos(portal):
    from app.models import SessaoPortalCliente
    from app.services import portal_cliente as s
    p=portal;ativar(p);pedido=iniciar(p)
    sessao=p.db.scalar(select(SessaoPortalCliente));sessao.expira_em=s.agora()+timedelta(hours=8,minutes=-11);p.db.commit()
    assert call(p,'troca-email/confirmar-atual',pedido)[0]==403
    p.token=logar(p,cadastro())
    novo=atual(p,pedido)
    assert call(p,'troca-email/confirmar-novo',novo)[0]==200
