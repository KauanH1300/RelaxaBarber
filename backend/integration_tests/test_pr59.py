"""Sem antecipação: HTTP real e concorrência no PostgreSQL local descartável."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso, ator, disputar, contagens
from test_financeiro_http import api, requisitar, pagamento
from test_seguranca_horarios import chamar
from test_reagendamento import corrida
from test_habilitacao_portal import portal


@pytest.fixture
def reserva(pg, caso):
    with pg.begin() as c:
        c.execute(text("UPDATE comandas SET status='aberta', data_fechamento=NULL WHERE id=:comanda"), caso)
        c.execute(text("UPDATE agendamentos SET status='aguardando' WHERE id=:agendamento"), caso)
    return caso


def body(valor='10.00'):
    return {'pagamentos': [pagamento(valor=valor) | {'confirmado': True}]}


def estado(pg, s, status):
    with pg.begin() as c:
        c.execute(text('UPDATE agendamentos SET status=:status WHERE id=:agendamento'), s | {'status': status})


@pytest.mark.parametrize('endpoint', ['recebimentos', 'fechamento-financeiro'])
@pytest.mark.parametrize('status', ['pendente', 'aguardando', 'em_atendimento', 'concluido', 'cancelado'])
def test_endpoints_estados(api, pg, reserva, endpoint, status):
    s = reserva
    estado(pg, s, status)
    permitido = status in ('em_atendimento', 'concluido')
    r = requisitar(api, s, endpoint, body=body('30.50'), key=uuid4())
    assert r[0] == (200 if permitido else 409), r
    assert contagens(pg) == ((1, 0, 1) if permitido else (0, 0, 0))
    if not permitido:
        assert r[1]['detail']['codigo'] == 'estado_financeiro_incompativel'


@pytest.mark.parametrize('endpoint', ['recebimentos', 'fechamento-financeiro'])
@pytest.mark.parametrize('situacao', ['sem_controle', 'fechada', 'comanda_cancelada'])
def test_demais_bloqueios_preservados(api, pg, reserva, endpoint, situacao):
    from test_financeiro_persistencia import fechar
    estado(pg, reserva, 'em_atendimento')
    with pg.begin() as c:
        if situacao == 'sem_controle':
            # Nova comanda sem controle, sem modificar um controle imutável.
            from test_financeiro_persistencia import criar_comanda
            nova = criar_comanda(c, reserva, dia='2099-01-03')
            reserva = reserva | {'comanda': nova['comanda']}
        elif situacao == 'comanda_cancelada':
            c.execute(text("UPDATE comandas SET status='cancelada' WHERE id=:comanda"), reserva)
        else:
            from test_financeiro_persistencia import pagar
            pagar(c, reserva, valor='30.50')
            fechar(c, reserva)
    antes = contagens(pg)
    assert requisitar(api, reserva, endpoint, body=body('30.50'), key=uuid4())[0] == 409
    assert contagens(pg) == antes


@pytest.mark.parametrize('endpoint', ['recebimentos', 'fechamento-financeiro'])
@pytest.mark.parametrize('status', ['pendente', 'aguardando', 'cancelado'])
def test_replay_historico_antes_da_nova_elegibilidade(api, pg, reserva, endpoint, status):
    """Fixture histórica explícita: inserção imutável com contrato/fingerprint real."""
    from app.models import PagamentoComanda, FechamentoFinanceiroComanda
    from app.services.regras_financeiras import fingerprint
    from uuid import uuid5
    s, chave, payload = reserva, uuid4(), body('30.50')
    p = payload['pagamentos'][0]
    dados = dict(valor=Decimal(p['valor']), forma=p['forma'], recebido_em=datetime.fromisoformat(p['recebido_em']))
    fp_p = fingerprint('pagamento', comanda_id=s['comanda'], **dados)
    fp = fingerprint('recebimentos_confirmados_v1' if endpoint == 'recebimentos' else 'fechamento_integral_v1',
        comanda_id=s['comanda'], pagamentos=[fp_p], **({} if endpoint == 'recebimentos' else {'motivo': None}))
    with Session(pg) as db:
        db.add(PagamentoComanda(comanda_id=s['comanda'], filial_id=s['filial'], registrado_por=s['atores']['recepcao'],
            chave_idempotencia=uuid5(chave, f"recebimento:{s['comanda']}:0" if endpoint == 'recebimentos' else f"{s['comanda']}:0"),
            fingerprint=fp if endpoint == 'recebimentos' else fp_p, **dados))
        db.flush()
        db.add(FechamentoFinanceiroComanda(comanda_id=s['comanda'], filial_id=s['filial'], total=Decimal('30.50'),
            recebido_liquido=Decimal('30.50'), motivo=None, registrado_por=s['atores']['recepcao'],
            chave_idempotencia=chave, fingerprint=fp))
        db.commit()
    estado(pg, s, status)
    antes = contagens(pg)
    r = requisitar(api, s, endpoint, body=payload, key=chave)
    assert r[0] == 200, r
    assert requisitar(api, s, endpoint, body=payload, key=chave) == r
    assert requisitar(api, s, endpoint, body=body('1.00'), key=chave)[0] == 409
    assert requisitar(api, s, endpoint, body=payload, key=uuid4())[0] == 409
    assert contagens(pg) == antes == (1, 0, 1)


def versao(pg, s):
    with pg.connect() as c:
        return c.scalar(text('SELECT atualizado_em FROM agendamentos WHERE id=:agendamento'), s)


def cancelar(db, s, v):
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    return atualizar_status(s['agendamento'], AgendamentoStatusUpdate(status='cancelado',
        motivo_cancelamento='Cliente solicitou cancelamento', confirmado=True, atualizado_em_esperado=v),
        db, ator(db, s), s['filial'])


def test_cancelamento_concorrente_uma_unica_autoria(runtime_pg, pg, reserva):
    s, v = reserva, versao(pg, reserva)
    assert corrida(runtime_pg, lambda db: cancelar(db, s, v), lambda db: cancelar(db, s, v)) == 'ConflitoEstadoAgendamento'
    with pg.connect() as c:
        r = c.execute(text('SELECT status,cancelado_por,cancelado_em,motivo_cancelamento FROM agendamentos WHERE id=:agendamento'), s).one()
        assert r.status == 'cancelado' and r.cancelado_por == s['atores']['recepcao']
        assert r.cancelado_em and r.motivo_cancelamento
        assert c.scalar(text('SELECT count(*) FROM itens_comanda WHERE comanda_id=:comanda'), s) == 1
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize('primeiro', ['cancelamento', 'inicio'])
def test_cancelamento_disputa_inicio(runtime_pg, pg, reserva, primeiro):
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    s, v = reserva, versao(pg, reserva)
    inicio = lambda db: atualizar_status(s['agendamento'], AgendamentoStatusUpdate(status='em_atendimento'), db, ator(db, s), s['filial'])
    cancel = lambda db: cancelar(db, s, v)
    assert corrida(runtime_pg, cancel if primeiro == 'cancelamento' else inicio,
                   inicio if primeiro == 'cancelamento' else cancel) in ('AgendamentoInvalido', 'ConflitoEstadoAgendamento')


@pytest.mark.parametrize('endpoint', ['recebimentos', 'fechamento-financeiro'])
def test_recebimentos_concorrentes_replay_e_nova_chave(runtime_pg, pg, reserva, endpoint):
    from app.services.financeiro import registrar_recebimentos, fechar_comanda
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s, chave, parcelas = reserva, uuid4(), [dict(valor=Decimal('30.50'), forma='dinheiro',
        recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1), confirmado=True)]
    estado(pg, s, 'em_atendimento')
    fn = registrar_recebimentos if endpoint == 'recebimentos' else fechar_comanda
    def executar(db, key=chave):
        return fn(s['comanda'], pagamentos=parcelas, chave_idempotencia=key, db=db, usuario=ator(db, s), filial_id=s['filial'])
    um, dois = disputar(runtime_pg, executar, executar)
    assert um == dois
    with Session(runtime_pg) as db, pytest.raises(EstadoFinanceiroIncompativel):
        executar(db, uuid4())
    assert contagens(pg) == (1, 0, 1)


@pytest.mark.parametrize('perfil', ['admin', 'recepcao', 'barbeiro', 'outro'])
def test_cancelamento_http_contrato_versao_historico_e_permissoes(api, pg, reserva, perfil):
    from app.core.security import criar_token
    s = reserva
    v = versao(pg, s).isoformat()
    token = criar_token(s['atores'][perfil])
    path = f"/agendamentos/{s['agendamento']}/status?filial_id={s['filial']}"
    payload = dict(status='cancelado', confirmado=True, motivo_cancelamento='Desistência conferida', atualizado_em_esperado=v)
    for mudanca in ({'confirmado': False}, {'motivo_cancelamento': ' '}, {'atualizado_em_esperado': None}):
        assert chamar(api, path, method='PATCH', token=token, dados=payload | mudanca)[0] == 422
    if perfil != 'outro':
        r = chamar(api, path, method='PATCH', token=token, dados=payload | {'atualizado_em_esperado': '2000-01-01T00:00:00Z'})
        assert r[0] == 409, r
    r = chamar(api, path, method='PATCH', token=token, dados=payload)
    assert r[0] == (404 if perfil == 'outro' else 200), r
    if perfil == 'outro': return
    assert r[1]['motivo_cancelamento'] == payload['motivo_cancelamento']
    assert r[1]['cancelado_por'] == str(s['atores'][perfil])
    assert chamar(api, path, method='PATCH', token=token, dados=payload)[0] == 409
    dia = '2099-01-01'
    assert chamar(api, f'/agendamentos?data={dia}&filial_id={s["filial"]}', token=token)[1] == []
    lista = chamar(api, f'/agendamentos?data={dia}&filial_id={s["filial"]}&incluir_cancelados=true', token=token)
    assert lista[0] == 200 and lista[1][0]['status'] == 'cancelado'
    assert lista[1][0]['motivo_cancelamento'] == payload['motivo_cancelamento']
    assert contagens(pg) == (0, 0, 0)


def test_cancelamento_historico_financeiro_continua_protegido(runtime_pg, pg, reserva):
    from test_financeiro_persistencia import pagar
    from app.services.errors import ConflitoEstadoAgendamento
    with pg.begin() as c: pagar(c, reserva)
    antes = contagens(pg)
    with Session(runtime_pg) as db, pytest.raises(ConflitoEstadoAgendamento):
        cancelar(db, reserva, versao(pg, reserva))
    assert contagens(pg) == antes


@pytest.mark.parametrize('endpoint', ['recebimentos', 'fechamento-financeiro'])
@pytest.mark.parametrize('primeira', ['inicio', 'cancelamento'])
def test_novo_recebimento_rele_estado_apos_lock(runtime_pg, pg, reserva, endpoint, primeira):
    from app.services.agendamento import atualizar_status
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.financeiro import registrar_recebimentos, fechar_comanda
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    s, v = reserva, versao(pg, reserva)
    def operar(db):
        if primeira == 'cancelamento': return cancelar(db, s, v)
        return atualizar_status(s['agendamento'], AgendamentoStatusUpdate(status='em_atendimento'), db, ator(db, s), s['filial'])
    def receber(db):
        fn = registrar_recebimentos if endpoint == 'recebimentos' else fechar_comanda
        return fn(s['comanda'], pagamentos=[dict(valor=Decimal('30.50'), forma='dinheiro', confirmado=True,
            recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1))], chave_idempotencia=uuid4(),
            db=db, usuario=ator(db, s), filial_id=s['filial'])
    _, resultado = disputar(runtime_pg, operar, receber)
    if primeira == 'cancelamento':
        assert isinstance(resultado, EstadoFinanceiroIncompativel)
        assert contagens(pg) == (0, 0, 0)
    else:
        assert not isinstance(resultado, Exception)
        assert contagens(pg) == (1, 0, 1)


@pytest.mark.parametrize('endpoint', ['recebimentos', 'fechamento-financeiro'])
def test_habilitacao_previa_nao_autoriza_pagamento(api, pg, runtime_pg, portal, endpoint):
    from test_habilitacao_portal import body as conferencia
    estado(pg, portal, 'aguardando')
    payload = conferencia(runtime_pg, portal)
    assert requisitar(api, portal, 'habilitacao-financeira', body=payload, key=uuid4())[0] == 200
    assert requisitar(api, portal, endpoint, body=body('30.50'), key=uuid4())[0] == 409
    assert contagens(pg) == (0, 0, 0)


def test_fechamento_de_quitacao_historica_sem_novos_pagamentos(api, pg, reserva):
    from test_financeiro_persistencia import pagar
    with pg.begin() as c: pagar(c, reserva, valor='30.50')
    chave = uuid4()
    r = requisitar(api, reserva, 'fechamento-financeiro', body={'pagamentos': []}, key=chave)
    assert r[0] == 200, r
    assert requisitar(api, reserva, 'fechamento-financeiro', body={'pagamentos': []}, key=chave) == r
    assert contagens(pg) == (1, 0, 1)
