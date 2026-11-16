"""ORM e HTTP em memória, sem .env ou conexão externa."""
import asyncio
from datetime import datetime, time, timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select, event, text
from sqlalchemy.exc import IntegrityError
from test_filiais import unidades, http_app, request


def dados(s, reserva=None, **changes):
    r = reserva or s.bookings[('barbeiro', 'A')]
    return dict(data='2099-01-02', hora_inicio='11:00', barbeiro_id=str(r.barbeiro_id),
                atualizado_em_esperado=r.atualizado_em.isoformat() if r.atualizado_em else None,
                motivo='  Cliente solicitou  ') | changes


def enviar(app, s, body=None, role='admin', reserva=None, filial=None, method='PATCH'):
    from app.core.security import criar_token
    r = reserva or s.bookings[('barbeiro', 'A')]
    path = f'/agendamentos/{r.id}/' + ('reagendamentos' if method == 'GET' else 'reagendamento')
    if filial: path += f'?filial_id={filial.id}'
    return asyncio.run(request(app, path, criar_token(s.users[role].id), method, body))


def test_preserva_reserva_comanda_financeiro_e_duracao(http_app, unidades):
    from app.models import Comanda, AgendamentoServico, ItemComanda, PagamentoComanda, Reagendamento
    s = unidades; r = s.bookings[('barbeiro', 'A')]
    c = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == r.id))
    # Pagamento pré-existente permanece no mesmo vínculo mesmo na troca de barbeiro.
    pagamento = PagamentoComanda(comanda_id=c.id, filial_id=c.filial_id, valor=Decimal('10.00'), forma='pix',
        recebido_em=datetime(2026, 1, 1, tzinfo=timezone.utc), registrado_por=s.users['admin'].id,
        chave_idempotencia=uuid4(), fingerprint='a' * 64)
    s.db.add(pagamento); s.db.commit()
    antes = (c.id, c.valor_total, c.cliente_id, c.status, c.controle_financeiro.registrado_em,
             [(i.id, i.preco_unitario) for i in c.itens], [(i.id, i.tempo_estimado, i.preco) for i in r.servicos])
    criado_por = r.criado_por
    s.service.tempo_estimado = 90; s.service.preco = Decimal('100.00'); s.db.commit()
    code, result = enviar(http_app, s, dados(s, barbeiro_id=str(s.users['itinerante'].id)))
    assert code == 200 and result['id'] == str(r.id) and result['hora_fim'] == '11:30:00'
    assert result['barbeiro']['id'] == str(s.users['itinerante'].id)
    s.db.refresh(c); s.db.refresh(r); s.db.refresh(pagamento)
    assert c.barbeiro_id == r.barbeiro_id == s.users['itinerante'].id
    assert antes == (c.id, c.valor_total, c.cliente_id, c.status, c.controle_financeiro.registrado_em,
                    [(i.id, i.preco_unitario) for i in c.itens], [(i.id, i.tempo_estimado, i.preco) for i in r.servicos])
    assert pagamento.comanda_id == c.id and pagamento.valor == Decimal('10.00') and r.criado_por == criado_por
    assert s.db.query(Comanda).count() == 5
    code, rows = enviar(http_app, s, method='GET')
    assert code == 200 and len(rows) == 1
    assert rows[0]['barbeiro_id_anterior'] == str(s.users['barbeiro'].id)
    assert rows[0]['data_anterior'] == '2099-01-01' and rows[0]['data_nova'] == '2099-01-02'
    assert rows[0]['motivo'] == 'Cliente solicitou' and rows[0]['registrado_por'] == str(s.users['admin'].id)


@pytest.mark.parametrize('role,target,allowed', [
    ('admin','itinerante',True), ('recepcao','itinerante',True), ('barbeiro','barbeiro',True),
    ('barbeiro_chefe','barbeiro_chefe',True), ('barbeiro','itinerante',False),
    ('barbeiro_chefe','itinerante',False),
])
def test_permissoes_origem_e_destino(http_app, unidades, role, target, allowed):
    s = unidades
    r = s.bookings[(role if role in ('barbeiro','barbeiro_chefe') else 'barbeiro', 'A')]
    code, _ = enviar(http_app, s, dados(s, r, barbeiro_id=str(s.users[target].id)), role, r)
    assert code == (200 if allowed else 403)
    if role in ('barbeiro', 'barbeiro_chefe'):
        # Chefe pode ler outras agendas, mas não pode reagendá-las.
        outro = s.bookings[('itinerante', 'A')]
        assert enviar(http_app, s, dados(s, outro), role, outro)[0] == 404


@pytest.mark.parametrize('status', ['concluido', 'cancelado', 'em_atendimento', 'desconhecido'])
def test_estado_bloqueado_sem_historico(http_app, unidades, status):
    from app.models import Reagendamento
    s = unidades; r = s.bookings[('barbeiro', 'A')]
    r.status = status; s.db.commit()
    assert enviar(http_app, s, dados(s))[0] == 409
    assert s.db.query(Reagendamento).count() == 0
    s.db.refresh(r); assert r.data.isoformat() == '2099-01-01'


def test_aguardando_comanda_aberta_e_versao_concorrente(http_app, unidades):
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.models import Comanda, Reagendamento
    s = unidades; r = s.bookings[('barbeiro', 'A')]
    atualizar_status(r.id, AgendamentoStatusUpdate(status='aguardando'), s.db, s.users['admin'])
    body = dados(s)
    assert enviar(http_app, s, body)[0] == 200
    assert enviar(http_app, s, body | {'hora_inicio': '15:00'})[0] == 409
    c = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == r.id))
    assert c.status == 'aberta' and s.db.query(Reagendamento).count() == 1


def test_escopo_filial_vinculo_e_sessao(http_app, unidades):
    from app.models import UsuarioFilial
    s = unidades; outro = s.bookings[('outro', 'B')]
    assert enviar(http_app, s, dados(s, outro), 'recepcao', outro)[0] == 404
    assert enviar(http_app, s, method='GET', role='recepcao', reserva=outro)[0] == 404
    assert enviar(http_app, s, dados(s), filial=s.b)[0] == 404
    assert enviar(http_app, s, dados(s, barbeiro_id=str(s.users['outro'].id)))[0] == 403
    link = s.db.scalar(select(UsuarioFilial).where(UsuarioFilial.usuario_id == s.users['recepcao'].id))
    link.ativo = False; s.db.commit()
    assert enviar(http_app, s, dados(s), 'recepcao')[0] == 404
    r = s.bookings[('barbeiro', 'A')]
    assert asyncio.run(request(http_app, f'/agendamentos/{r.id}/reagendamento', 'invalido', 'PATCH', dados(s)))[0] == 401


@pytest.mark.parametrize('changes', [
    {'data': '2000-01-01'}, {'hora_inicio': '23:45'}, {'hora_inicio': '11:00+03:00'},
    {'data': '9999-12-31', 'hora_inicio': '23:45'}, {'motivo': 'x'*1001}, {'cliente_id': str(uuid4())},
])
def test_entradas_invalidas(http_app, unidades, changes):
    assert enviar(http_app, unidades, dados(unidades, **changes))[0] == 422


def test_conflito_global_autoexclusao_e_horario_liberado(http_app, unidades):
    from app.services.agendamento import criar_agendamento
    s = unidades; r = s.bookings[('itinerante', 'A')]
    assert enviar(http_app, s, dados(s, r, data='2099-01-01', hora_inicio='10:00'), reserva=r)[0] == 409
    assert enviar(http_app, s, dados(s, r, data='2099-01-01', hora_inicio='09:15'), reserva=r)[0] == 200
    # Novo horário sobrepõe parte da própria reserva, mas libera o trecho anterior.
    assert enviar(http_app, s, dados(s, r, hora_inicio='15:00'), reserva=r)[0] == 200
    criar_agendamento(s.payload('itinerante', s.a, '09:00'), s.db, s.users['admin'])


def test_expediente_jornada_intervalo_e_folga(http_app, unidades):
    from app.services import horarios_filial, jornada
    from app.schemas.horario_filial import HorariosFilialUpdate
    from app.schemas.jornada import JornadaUpdate
    s = unidades
    semana = [dict(dia_semana=d, fechado=False, hora_inicio='08:00', hora_fim='18:00') for d in range(7)]
    horarios_filial.atualizar(s.db, s.users['admin'], s.a.id, HorariosFilialUpdate(dias=semana))
    dias = [d | {'hora_fim': '16:00', 'intervalos': [dict(dia_semana=d['dia_semana'], fechado=False, hora_inicio='12:00', hora_fim='13:00')]} for d in semana]
    jornada.atualizar(s.db, s.users['admin'], s.a.id, s.users['barbeiro'].id, JornadaUpdate(dias=dias,
        excecoes=[dict(data='2099-01-03', dia_semana=5, fechado=True)]))
    for change in [dict(hora_inicio='07:59'), dict(hora_inicio='15:45'), dict(hora_inicio='12:00'), dict(data='2099-01-03')]:
        assert enviar(http_app, s, dados(s, **change))[0] == 422
    assert enviar(http_app, s, dados(s, hora_inicio='13:00'))[0] == 200


def test_vencido_comanda_incompativel_e_sem_alteracao(http_app, unidades, monkeypatch):
    from app.services import agendamento
    from app.models import Comanda
    s = unidades; r = s.bookings[('barbeiro', 'A')]
    assert enviar(http_app, s, dados(s, data='2099-01-01', hora_inicio='09:00'))[0] == 409
    c = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == r.id))
    c.status = 'fechada'; s.db.commit()
    assert enviar(http_app, s, dados(s))[0] == 409
    c.status = 'pendente'; s.db.commit()
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime(2099, 1, 1, 10, tzinfo=agendamento.FUSO_BARBEARIA))
    assert enviar(http_app, s, dados(s))[0] == 409


def test_rollback_preserva_todos_os_vinculos(unidades):
    from app.models import Comanda, Reagendamento
    from app.services.reagendamento import reagendar
    from app.schemas.reagendamento import ReagendamentoUpdate
    from app.services.persistencia import FalhaPersistencia
    s = unidades; r = s.bookings[('barbeiro', 'A')]
    body = ReagendamentoUpdate(**dados(s, barbeiro_id=str(s.users['itinerante'].id)))
    def falhar(session):
        session.flush()
        raise IntegrityError('simulado', {}, Exception('falha antes do commit'))
    event.listen(s.db, 'before_commit', falhar)
    try:
        with pytest.raises(FalhaPersistencia): reagendar(r.id, body, s.db, s.users['admin'])
    finally: event.remove(s.db, 'before_commit', falhar)
    s.db.refresh(r)
    c = s.db.scalar(select(Comanda).where(Comanda.agendamento_id == r.id))
    assert r.data.isoformat() == '2099-01-01' and r.barbeiro_id == c.barbeiro_id == s.users['barbeiro'].id
    assert s.db.query(Reagendamento).count() == 0
