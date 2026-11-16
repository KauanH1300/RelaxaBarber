from uuid import uuid4
import pytest
from sqlalchemy import select
from test_reserva_publica import reserva,api,dados  # noqa:F401
from test_portal_clientes import portal  # noqa:F401


def configurar(p,ids,barbeiro=None,filial=None):
    from app.schemas.reserva_publica import RestricoesUpdate
    from app.services.reserva_publica import configurar_restricoes
    return configurar_restricoes(p.db,p.admin,filial or p.f.id,barbeiro or p.a.id,RestricoesUpdate(servicos=ids))


def test_padrao_novos_servicos_e_legado_preservado(reserva):
    from app.models import Servico
    from app.models.reserva_portal import HabilitacaoServico
    p=reserva
    novo=Servico(nome='Novo',preco=25,tempo_estimado=15,comissao_padrao=10)
    p.db.add(novo);p.db.commit()
    configurar(p,[p.s.id])
    ids=lambda servico:{r['id'] for r in api(p,f'/publico/barbeiros?servico_id={servico}')[1]}
    assert ids(p.s.id)=={str(p.b.id)}
    assert ids(novo.id)=={str(p.a.id),str(p.b.id)}
    assert api(p,'/portal-clientes/reservas',dados(p,servico_id=str(novo.id)),'POST')[0]==201
    assert p.db.query(HabilitacaoServico).count()==1  # positive legacy row was not inverted


def test_restricao_e_revalidada_qualquer_e_sem_horarios(reserva):
    p=reserva
    assert len(api(p,f'/publico/barbeiros?servico_id={p.s.id}')[1])==2
    configurar(p,[p.s.id])
    assert api(p,'/portal-clientes/reservas',dados(p),'POST')[0]==409
    code,out,_=api(p,'/portal-clientes/reservas',dados(p,barbeiro_id=None),'POST')
    assert code==201 and out['barbeiro']['id']==str(p.b.id)
    # Being capable of a service does not promise a free slot.
    assert api(p,f'/publico/horarios?servico_id={p.s.id}&data=2000-01-01')[1]['horarios']==[]
    assert len(api(p,f'/publico/barbeiros?servico_id={p.s.id}')[1])==1
    configurar(p,[])
    assert len(api(p,f'/publico/barbeiros?servico_id={p.s.id}')[1])==2


def test_excecoes_isoladas_por_filial_e_vinculo(reserva):
    from app.models import Filial,UsuarioFilial
    from app.services.reserva_publica import profissionais,consultar_restricoes
    from app.services.errors import SemPermissao
    p=reserva;outra=Filial(nome='Outra',empresa_id=p.f.empresa_id)
    p.db.add(outra);p.db.flush();p.db.add(UsuarioFilial(usuario_id=p.a.id,filial_id=outra.id));p.db.commit()
    configurar(p,[p.s.id])
    assert {u.id for u in profissionais(p.db,outra.id,p.s.id)}=={p.a.id}
    configurar(p,[p.s.id],filial=outra.id)
    configurar(p,[])
    assert {u.id for u in profissionais(p.db,p.f.id,p.s.id)}=={p.a.id,p.b.id}
    assert profissionais(p.db,outra.id,p.s.id)==[]
    assert consultar_restricoes(p.db,p.admin,outra.id,p.a.id)['restricoes']==[p.s.id]
    with pytest.raises(SemPermissao):configurar(p,[],barbeiro=p.b.id,filial=outra.id)


def test_api_admin_schema_sem_dados_internos_e_legado_recusado(reserva):
    from app.core.security import criar_token
    from app.models.reserva_portal import RestricaoServico
    p=reserva;url=f'/filiais/{p.f.id}/barbeiros/{p.a.id}/restricoes-servicos'
    assert api(p,url)[0]==401
    assert api(p,url,token=criar_token(p.a.id))[0]==403
    token=criar_token(p.admin.id)
    assert api(p,url,{'servicos':[str(p.s.id)]},'PUT',token=token)[0]==200
    code,out,_=api(p,url,token=token)
    assert code==200 and out['restricoes']==[str(p.s.id)]
    assert set(out['servicos'][0])=={'id','nome','ativo'}
    assert api(p,url,{'servicos':[str(uuid4())]},'PUT',token=token)[0]==404
    assert p.db.query(RestricaoServico).count()==1  # invalid replacement rolls back
    assert api(p,url,{'servicos':[],'filial_id':str(uuid4())},'PUT',token=token)[0]==422
    assert api(p,f'/filiais/{p.f.id}/barbeiros/{p.a.id}/servicos',{'servicos':[]},'PUT',token=token)[0]==410


def test_servico_inativo_mantem_restricao_apos_reativacao(reserva):
    from app.services.reserva_publica import profissionais
    p=reserva;configurar(p,[p.s.id]);p.s.ativo=False;p.db.commit()
    configurar(p,[p.s.id]);p.s.ativo=True;p.db.commit()
    assert {u.id for u in profissionais(p.db,p.f.id,p.s.id)}=={p.b.id}


def test_falha_transacional_preserva_excecoes_anteriores(reserva):
    from sqlalchemy import event
    from app.models.reserva_portal import RestricaoServico
    p=reserva;configurar(p,[p.s.id])
    def falhar(session):raise RuntimeError('falha injetada')
    event.listen(p.db,'before_commit',falhar)
    try:
        with pytest.raises(RuntimeError):configurar(p,[])
    finally:event.remove(p.db,'before_commit',falhar)
    assert p.db.scalars(select(RestricaoServico.servico_id)).all()==[p.s.id]
