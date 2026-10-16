"""Gestão mínima por HTTP/ORM; sem exclusão de históricos ou privilégios em JWT."""
import asyncio
from datetime import datetime

import pytest
from sqlalchemy import select, event
from sqlalchemy.exc import IntegrityError

from test_filiais import unidades, http_app, request


@pytest.mark.parametrize('role', ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'])
def test_endpoints_gestao_sao_admin(http_app, unidades, role):
    from app.core.security import criar_token
    s = unidades
    token = criar_token(s.users[role].id)
    for path, method, body in (
        (f'/filiais/{s.a.id}/usuarios', 'GET', None),
        (f'/filiais/{s.a.id}/usuarios/{s.users["barbeiro"].id}', 'PUT', {'ativo': False}),
        (f'/filiais/{s.a.id}', 'DELETE', None),
    ):
        code, _ = asyncio.run(request(http_app, path, token, method, body))
        assert code == ((200 if method == 'GET' else 409) if role == 'admin' else 403)


def test_cria_desativa_reativa_sem_duplicar_e_revoga_jwt(http_app, unidades):
    from app.core.security import criar_token
    from app.models import UsuarioFilial
    s = unidades
    admin = criar_token(s.users['admin'].id)
    path = f'/filiais/{s.b.id}/usuarios/{s.users["recepcao"].id}'
    code, created = asyncio.run(request(http_app, path, admin, 'PUT', {'ativo': True}))
    assert code == 200 and created['ativo']
    token = criar_token(s.users['recepcao'].id)
    assert asyncio.run(request(http_app, f'/agendamentos?data=2099-01-01&filial_id={s.b.id}', token))[0] == 200
    code, disabled = asyncio.run(request(http_app, path, admin, 'PUT', {'ativo': False}))
    assert code == 200 and not disabled['ativo'] and disabled['id'] == created['id']
    assert asyncio.run(request(http_app, f'/agendamentos?data=2099-01-01&filial_id={s.b.id}', token))[0] == 403
    assert asyncio.run(request(http_app, f'/agendamentos?data=2099-01-01&filial_id={s.a.id}', token))[0] == 200
    for _ in range(2):
        code, restored = asyncio.run(request(http_app, path, admin, 'PUT', {'ativo': True}))
        assert code == 200 and restored['id'] == created['id']
    assert s.db.query(UsuarioFilial).filter(UsuarioFilial.usuario_id == s.users['recepcao'].id, UsuarioFilial.filial_id == s.b.id).count() == 1


def test_desativacao_bloqueia_futuro_mesmo_apos_mudanca_de_perfil(unidades):
    from app.services.gestao_filiais import definir_vinculo
    from app.services.errors import ConflitoGestaoFilial
    s = unidades
    s.users['barbeiro'].perfil = 'recepcao'
    s.db.commit()
    with pytest.raises(ConflitoGestaoFilial):
        definir_vinculo(s.db, s.users['admin'], s.a.id, s.users['barbeiro'].id, False)


def test_desativa_unidade_apos_resolver_reservas_sem_alterar_historico(http_app, unidades):
    from app.core.security import criar_token
    from app.models import Agendamento, Comanda, ClienteFilial
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s = unidades
    for (role, unit), appointment in s.bookings.items():
        if unit == 'A':
            atualizar_status(appointment.id, AgendamentoStatusUpdate(status='cancelado'), s.db, s.users['admin'])
    before = (s.db.query(Agendamento).count(), s.db.query(Comanda).count(), s.db.query(ClienteFilial).count())
    token = criar_token(s.users['admin'].id)
    assert asyncio.run(request(http_app, f'/filiais/{s.a.id}', token, 'DELETE'))[0] == 204
    assert not s.a.ativa
    assert (s.db.query(Agendamento).count(), s.db.query(Comanda).count(), s.db.query(ClienteFilial).count()) == before
    assert asyncio.run(request(http_app, f'/agendamentos?data=2099-01-01&filial_id={s.a.id}', token))[0] == 403
    assert asyncio.run(request(http_app, f'/agendamentos?data=2099-01-01&filial_id={s.b.id}', token))[0] == 200


@pytest.mark.parametrize('status,day,hour,blocked', [
    ('pendente', '2099-01-02', 12, True), ('cancelado', '2099-01-02', 12, False),
    ('concluido', '2099-01-02', 12, False), ('em_atendimento', '2098-12-31', 12, True),
    ('pendente', '2099-01-01', 9, True), ('pendente', '2099-01-01', 10, False),
])
def test_guarda_de_horarios_e_estados(unidades, monkeypatch, status, day, hour, blocked):
    from app.services import agendamento
    from app.services.gestao_filiais import definir_vinculo
    from app.services.errors import ConflitoGestaoFilial
    from datetime import date
    s = unidades
    target = s.bookings[('barbeiro', 'A')]
    target.status = status
    target.data = date.fromisoformat(day)
    s.db.commit()
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime(2099, 1, 1, hour, 15, tzinfo=agendamento.FUSO_BARBEARIA))
    if blocked:
        with pytest.raises(ConflitoGestaoFilial): definir_vinculo(s.db, s.users['admin'], s.a.id, s.users['barbeiro'].id, False)
    else:
        assert not definir_vinculo(s.db, s.users['admin'], s.a.id, s.users['barbeiro'].id, False).ativo


@pytest.mark.parametrize('novo', [True, False])
def test_falha_commit_reverte_gestao_vinculo(unidades, novo):
    from app.services.gestao_filiais import definir_vinculo
    from app.services.persistencia import FalhaPersistencia
    from app.models import UsuarioFilial
    s = unidades
    unit = s.b if novo else s.a
    before = s.db.query(UsuarioFilial).count()
    def fail(db):
        db.flush()
        raise IntegrityError('teste', {}, Exception('falha induzida'))
    event.listen(s.db, 'before_commit', fail)
    try:
        with pytest.raises(FalhaPersistencia): definir_vinculo(s.db, s.users['admin'], unit.id, s.users['recepcao'].id, novo)
    finally:
        event.remove(s.db, 'before_commit', fail)
    assert s.db.query(UsuarioFilial).count() == before
    link = s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == s.users['recepcao'].id, UsuarioFilial.filial_id == s.a.id))
    assert link.ativo


@pytest.mark.parametrize('inativo', ['usuario', 'filial', 'empresa'])
def test_reativacao_exige_usuario_filial_e_empresa_ativos(unidades, inativo):
    from app.services.gestao_filiais import definir_vinculo
    from app.services.errors import ConflitoGestaoFilial
    from app.models import UsuarioFilial
    s = unidades
    link = definir_vinculo(s.db, s.users['admin'], s.b.id, s.users['recepcao'].id, True)
    original = (link.id, link.data_cadastro)
    definir_vinculo(s.db, s.users['admin'], s.b.id, s.users['recepcao'].id, False)
    target = {'usuario': s.users['recepcao'], 'filial': s.b, 'empresa': s.b.empresa}[inativo]
    setattr(target, 'ativo' if inativo == 'usuario' else 'ativa', False)
    s.db.commit()
    with pytest.raises(ConflitoGestaoFilial):
        definir_vinculo(s.db, s.users['admin'], s.b.id, s.users['recepcao'].id, True)
    s.db.refresh(link)
    assert not link.ativo and (link.id, link.data_cadastro) == original
    assert s.db.query(UsuarioFilial).filter_by(usuario_id=link.usuario_id, filial_id=link.filial_id).count() == 1


@pytest.mark.parametrize('role', ['recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_remover_ultimo_vinculo_bloqueia_operacoes_com_jwt_valido(http_app, unidades, role):
    from app.core.security import criar_token
    from app.models import Comanda
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s = unidades
    token = criar_token(s.users[role].id)
    admin = criar_token(s.users['admin'].id)
    appointment = s.bookings[('barbeiro' if role == 'recepcao' else role, 'A')]
    command = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == appointment.id))
    if role != 'recepcao':
        atualizar_status(appointment.id, AgendamentoStatusUpdate(status='cancelado'), s.db, s.users['admin'])
    path = f'/filiais/{s.a.id}/usuarios/{s.users[role].id}'
    assert asyncio.run(request(http_app, path, admin, 'PUT', {'ativo': False}))[0] == 200
    assert asyncio.run(request(http_app, '/filiais', token)) == (200, [])
    for path in ('/agendamentos?data=2099-01-01', '/comandas', '/usuarios/barbeiros', '/clientes', '/clientes/pesquisa'):
        assert asyncio.run(request(http_app, path, token))[0] == 403
    for path in (f'/agendamentos/{appointment.id}', f'/comandas/{command.id}'):
        assert asyncio.run(request(http_app, path, token))[0] == 404
    assert asyncio.run(request(http_app, f'/agendamentos/{appointment.id}/status', token, 'PATCH', {'status': 'aguardando'}))[0] == 404


def test_uuid_de_outra_filial_nao_pode_ser_operado_no_contexto_atual(http_app, unidades):
    from app.core.security import criar_token
    from app.models import Comanda
    s = unidades
    token = criar_token(s.users['admin'].id)
    appointment = s.bookings[('barbeiro', 'A')]
    command = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == appointment.id))
    for path in (f'/agendamentos/{appointment.id}', f'/comandas/{command.id}'):
        assert asyncio.run(request(http_app, f'{path}?filial_id={s.b.id}', token))[0] == 404
    assert asyncio.run(request(http_app, f'/agendamentos/{appointment.id}/status?filial_id={s.b.id}', token, 'PATCH', {'status': 'cancelado'}))[0] == 404
    assert appointment.status == 'pendente' and appointment.filial_id == s.a.id
