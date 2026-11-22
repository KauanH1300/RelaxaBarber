from datetime import date, datetime, time

import pytest
from sqlalchemy.orm import Session

from test_complementos_agenda import api, data, duas_filiais, requisitar
from test_minha_agenda import minha, pedido
from test_reserva_publica import agenda, payload


def bloquear_intervalo(db, s, profissional, dia, inicio, fim):
    from app.models import BloqueioAgenda

    db.add(BloqueioAgenda(filial_id=s['filial'], barbeiro_id=profissional, data=dia,
                          hora_inicio=inicio, hora_fim=fim, motivo='Bloqueio de teste',
                          criado_por=profissional))


@pytest.mark.parametrize('fluxo', ['criacao', 'remarcacao'])
@pytest.mark.parametrize('modo', ['melhor', 'empate', 'explicito', 'restrito', 'ocupado'])
def test_distribuicao_portal(request, agenda, pg, fluxo, modo):
    from app.models.reserva_portal import RestricaoServico
    from app.services import minha_agenda, reserva_publica

    s = request.getfixturevalue('minha') if fluxo == 'remarcacao' else agenda
    primeiro, segundo = sorted((s['user'], s['other']), key=str)
    dia = date(2099, 5, 21)
    with Session(pg) as db, db.begin():
        if modo != 'empate':
            # O segundo ID tem encaixe exato. O primeiro tem um intervalo maior.
            bloquear_intervalo(db, s, segundo, dia, time(8), time(9))
            bloquear_intervalo(db, s, segundo, dia, time(9, 30), time(18))
        if modo == 'restrito':
            db.add(RestricaoServico(filial_id=s['filial'], barbeiro_id=segundo, servico_id=s['service']))
        if modo == 'ocupado':
            bloquear_intervalo(db, s, segundo, dia, time(9), time(9, 30))

    escolhas = dict(data=dia, hora_inicio=time(9), barbeiro_id=primeiro if modo == 'explicito' else None)
    esperado = segundo if modo == 'melhor' else primeiro
    with Session(s['engine']) as db:
        if fluxo == 'criacao':
            dados = payload(s, **escolhas)
            resultado = reserva_publica.confirmar(db, dados, s['token'])
            assert reserva_publica.confirmar(db, dados, s['token']).id == resultado.id
        else:
            resultado = minha_agenda.remarcar(db, s['token'], s['id'], pedido(s, **escolhas))
            assert resultado.id == s['id']
    assert resultado.barbeiro.id == esperado


def test_sugestoes_internas_respeitam_escopo_duracao_e_preservam_escolha_manual(
    api, pg, agenda, duas_filiais, monkeypatch,
):
    from app.models.reserva_portal import RestricaoServico
    from app.services import agendamento

    s = duas_filiais
    dia = date(2099, 5, 20)
    monkeypatch.setattr(agendamento, 'agora_local',
                        lambda: datetime.combine(dia, time(8), agendamento.FUSO_BARBEARIA))
    regras = dict(antecedencia_reserva_horas=2, antecedencia_maxima_reserva_dias=1,
                  antecedencia_cancelamento_horas=1)
    assert requisitar(api, f"/filiais/{s['filial']}/antecedencia", s['admin'], method='PUT', dados=regras)[0] == 200
    with Session(pg) as db, db.begin():
        db.add(RestricaoServico(filial_id=s['filial'], barbeiro_id=s['user'], servico_id=s['service']))
        bloquear_intervalo(db, s, s['other'], dia, time(8), time(9))
        bloquear_intervalo(db, s, s['other'], dia, time(9, 30), time(18))

    rota = '/agendamentos/sugestoes'
    filtros = dict(filial_id=s['filial'], data=dia, servicos_ids=s['service'])
    codigo, sugestoes = requisitar(api, rota, s['admin'], duracao_min=20, **filtros)
    assert codigo == 200 and [(x['barbeiro_id'], x['hora_inicio']) for x in sugestoes] == [(str(s['other']), '09:00')]
    assert requisitar(api, rota, s['admin'], duracao_min=35, **filtros) == (200, [])
    assert requisitar(api, rota, s['user'], duracao_min=20, **filtros) == (200, [])

    entrada = payload(agenda, data=dia).model_dump(mode='json', exclude_none=True)
    entrada = {k: entrada[k] for k in ('data', 'hora_inicio', 'barbeiro_id')} | {
        'filial_id': str(s['filial']), 'cliente_id': str(s['client']),
        'servicos': [{'servico_id': str(s['service'])}], 'duracao_min': 20,
    }
    codigo, reserva = requisitar(api, '/agendamentos', s['admin'], method='POST', dados=entrada)
    assert codigo == 201 and reserva['barbeiro_id'] == str(s['user'])
    remarcacao = dict(agendamento_id=reserva['id'], filial_id=s['filial'], data=dia)
    assert requisitar(api, rota, s['admin'], **remarcacao) == (200, sugestoes)
    assert requisitar(api, rota, s['other'], **remarcacao)[0] == 404
