import asyncio

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, OperationalError

from test_filiais import unidades, http_app, request


def payload(user, **changes):
    return {**dict(nome=user.nome, email=user.email.replace('.test', '.com'), telefone=user.telefone,
                   perfil=user.perfil, ativo=user.ativo), **changes}


@pytest.mark.parametrize('role', ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_edicao_e_promocao_somente_admin(http_app, unidades, role):
    from app.core.security import criar_token
    s = unidades
    target = s.users['recepcao']
    code, body = asyncio.run(request(http_app, f'/usuarios/{target.id}', criar_token(s.users[role].id),
                                    'PATCH', payload(target, perfil='admin', nome='Recepção atualizada')))
    assert code == (200 if role == 'admin' else 403)
    assert target.perfil == ('admin' if role == 'admin' else 'recepcao')
    if code == 200:
        assert body['nome'] == 'Recepção atualizada' and 'senha_hash' not in body


@pytest.mark.parametrize('changes', [{'ativo': False}, {'perfil': 'recepcao'}])
def test_nao_remove_proprio_admin(http_app, unidades, changes):
    from app.core.security import criar_token
    s = unidades; admin = s.users['admin']
    code, _ = asyncio.run(request(http_app, f'/usuarios/{admin.id}', criar_token(admin.id), 'PATCH', payload(admin, **changes)))
    assert code == 409 and admin.ativo and admin.perfil == 'admin'


@pytest.mark.parametrize('role', ['barbeiro', 'itinerante', 'outro'])
@pytest.mark.parametrize('changes', [{'ativo': False}, {'perfil': 'recepcao'}])
def test_reservas_futuras_bloqueiam_em_todas_filiais(http_app, unidades, role, changes):
    from app.core.security import criar_token
    s = unidades; user = s.users[role]
    code, _ = asyncio.run(request(http_app, f'/usuarios/{user.id}', criar_token(s.users['admin'].id), 'PATCH', payload(user, **changes)))
    assert code == 409 and user.ativo and user.perfil == 'barbeiro'


def test_inativacao_preserva_historico_revoga_sessao_e_reativa(http_app, unidades):
    from app.models import Agendamento, Comanda, UsuarioFilial
    from app.core.security import criar_token
    s = unidades; user = s.users['recepcao']; token = criar_token(user.id)
    before = [s.db.query(m).count() for m in (Agendamento, Comanda, UsuarioFilial)]
    admin = criar_token(s.users['admin'].id)
    code, body = asyncio.run(request(http_app, f'/usuarios/{user.id}', admin, 'PATCH', payload(user, ativo=False)))
    assert code == 200 and not body['ativo']
    assert asyncio.run(request(http_app, '/filiais', token))[0] == 401
    assert [s.db.query(m).count() for m in (Agendamento, Comanda, UsuarioFilial)] == before
    assert asyncio.run(request(http_app, f'/usuarios/{user.id}', admin, 'PATCH', payload(user, ativo=True)))[0] == 200


def test_comanda_aberta_bloqueia_apos_conclusao(http_app, unidades):
    from app.core.security import criar_token
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s = unidades; user = s.users['barbeiro']
    for status in ('aguardando', 'em_atendimento', 'concluido'):
        atualizar_status(s.bookings[('barbeiro', 'A')].id, AgendamentoStatusUpdate(status=status), s.db, s.users['admin'])
    code, body = asyncio.run(request(http_app, f'/usuarios/{user.id}', criar_token(s.users['admin'].id), 'PATCH', payload(user, ativo=False)))
    assert code == 409 and 'comandas abertas' in body['detail'] and user.ativo


def test_colisao_email_e_campos_privados_rejeitados(http_app, unidades):
    from app.core.security import criar_token
    s = unidades; user = s.users['recepcao']; token = criar_token(s.users['admin'].id)
    # Normalize the stored email first, then attempt the conflicting write.
    admin = s.users['admin']; admin.email = 'admin@example.com'; s.db.commit()
    assert asyncio.run(request(http_app, f'/usuarios/{user.id}', token, 'PATCH', payload(user, email=admin.email)))[0] == 409
    for extra in [{'senha_hash': 'nao-permitido'}, {'filial_ids': []}, {'perfil': 'superadmin'}, {'nome': '  '}]:
        assert asyncio.run(request(http_app, f'/usuarios/{user.id}', token, 'PATCH', payload(user, **extra)))[0] == 422


def test_falha_commit_reverte_edicao(unidades):
    from app.services.gestao_usuarios import atualizar
    from app.services.persistencia import FalhaPersistencia
    from app.schemas.usuario import UsuarioUpdate
    s = unidades; user = s.users['recepcao']; original = user.nome
    def falhar(db):
        db.flush()
        raise IntegrityError('ficticio', {}, Exception('falha induzida'))
    event.listen(s.db, 'before_commit', falhar)
    try:
        with pytest.raises(FalhaPersistencia):
            atualizar(s.db, s.users['admin'], user.id, UsuarioUpdate(**payload(user, nome='Outro nome')))
    finally:
        event.remove(s.db, 'before_commit', falhar)
    s.db.refresh(user)
    assert user.nome == original


def test_lock_indisponivel_aborta_sem_mutacao(unidades, monkeypatch):
    from app.services.gestao_usuarios import atualizar
    from app.services.errors import ConflitoGestaoFilial
    from app.schemas.usuario import UsuarioUpdate
    s = unidades; user = s.users['recepcao']; original = user.nome
    class LockIndisponivel(Exception):
        pgcode = '55P03'
    def bloquear(*args, **kwargs):
        raise OperationalError('ficticio', {}, LockIndisponivel())
    with monkeypatch.context() as patch:
        patch.setattr(s.db, 'scalars', bloquear)
        with pytest.raises(ConflitoGestaoFilial, match='Cadastro em uso'):
            atualizar(s.db, s.users['admin'], user.id, UsuarioUpdate(**payload(user, nome='Outro nome')))
    s.db.refresh(user)
    assert user.nome == original
