from datetime import date, datetime, time
from urllib.parse import urlencode

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from test_concorrencia import data
from test_contexto_filiais import duas_filiais, payload
from test_financeiro_http import api
from test_reagendamento import corrida
from test_reserva_publica import agenda, payload as pedido_publico
from test_seguranca_horarios import chamar


def requisitar(api, caminho, ator, *, method='GET', dados=None, **params):
    from app.core.security import criar_token
    query = '?' + urlencode(params) if params else ''
    return chamar(api, caminho + query, method=method, dados=dados, token=criar_token(ator))


def bloqueio(s, dia='2099-01-01', inicio='09:00', fim='09:30'):
    return dict(filial_id=str(s['filial']), barbeiro_id=str(s['user']), data=dia,
                hora_inicio=inicio, hora_fim=fim, motivo='Manutenção')


def criar_recepcao(pg, s):
    from app.models import Usuario, UsuarioFilial, PerfilEnum
    with Session(pg) as db, db.begin():
        recepcao = Usuario(nome='Recepção', email='recepcao@example.test', senha_hash='ficticio', perfil=PerfilEnum.RECEPCAO)
        db.add(UsuarioFilial(usuario=recepcao, filial_id=s['filial']))
        db.flush()
        return recepcao.id


def test_bloqueios_isolados_autorizacao_disponibilidade_e_revogacao(api, pg, agenda, duas_filiais):
    from app.services.reserva_publica import listar_horarios
    s = duas_filiais
    recepcao = criar_recepcao(pg, s)
    data_bloqueio = '2099-05-20'
    path = '/agendamentos/bloqueios'
    dados = bloqueio(s, data_bloqueio)
    assert requisitar(api, path, s['other'], method='POST', dados=dados)[0] == 403
    assert requisitar(api, path, recepcao, method='POST', dados=dados)[0] == 403
    assert requisitar(api, path, s['user'], method='POST', dados=dados | {'motivo': '   '})[0] == 422
    code, item = requisitar(api, path, s['user'], method='POST', dados=dados)
    assert code == 201, item
    assert item['motivo'] == 'Manutenção'
    assert requisitar(api, path, s['admin'], method='POST', dados=dados)[0] == 409
    assert requisitar(api, path, s['admin'], filial_id=s['second'], data=data_bloqueio)[1] == []
    assert requisitar(api, path, s['other'], filial_id=s['filial'], data=data_bloqueio)[1] == []
    assert requisitar(api, path, recepcao, filial_id=s['filial'], data=data_bloqueio)[1][0]['id'] == item['id']
    disponibilidade = f"/filiais/{s['filial']}/barbeiros/{s['user']}/disponibilidade"
    code, slots = requisitar(api, disponibilidade, s['admin'], data=data_bloqueio, duracao=30)
    assert code == 200 and '09:00' not in slots['horarios'] and '09:30' in slots['horarios']
    with Session(agenda['engine']) as db:
        publico = listar_horarios(db, s['service'], date.fromisoformat(data_bloqueio), s['user'], s['filial'])
        assert publico['horarios'] == slots['horarios']
        assert set(publico['recomendados']) <= set(publico['horarios'])
        assert 'motivo' not in publico
    remover = path + '/' + item['id']
    assert requisitar(api, remover, s['other'], method='DELETE', filial_id=s['filial'])[0] == 403
    assert requisitar(api, remover, s['user'], method='DELETE', filial_id=s['filial'])[0] == 204
    assert requisitar(api, path, s['admin'], filial_id=s['filial'], data=data_bloqueio)[1] == []
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT revogado_por FROM bloqueios_agenda WHERE id=:id'), {'id': item['id']}) == s['user']
        for role in ('anon', 'authenticated', 'service_role'):
            assert not conn.scalar(text("SELECT has_table_privilege(:role,'public.bloqueios_agenda','SELECT')"), {'role': role})
        assert not conn.scalar(text("SELECT has_column_privilege('relaxabarber_runtime','public.bloqueios_agenda','motivo','UPDATE')"))


def test_bloqueio_confere_e_repete_operacoes_sem_duplicar(api, pg, duas_filiais):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4
    from app.core.security import criar_token
    from test_seguranca_horarios import chamar

    s = duas_filiais
    dados = bloqueio(s)
    rota = '/agendamentos/bloqueios'
    chave = str(uuid4())
    cabecalhos = [('Idempotency-Key', chave)]
    token = criar_token(s['user'])
    conferir = f'{rota}/cadastros/{chave}'
    assert requisitar(api, conferir, s['user'], filial_id=s['filial'])[0] == 404
    barreira = Barrier(2)

    def criar():
        barreira.wait(timeout=5)
        return chamar(api, rota, method='POST', dados=dados, token=token, cabecalhos=cabecalhos)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = [f.result(timeout=15) for f in [pool.submit(criar), pool.submit(criar)]]
    assert a == b and a[0] == 201
    ident = a[1]['id']
    assert chamar(api, rota, method='POST', dados=dados | {'motivo': 'Outro motivo'}, token=token, cabecalhos=cabecalhos)[0] == 409
    assert requisitar(api, conferir, s['user'], filial_id=s['filial']) == (200, a[1])
    assert requisitar(api, conferir, s['admin'], filial_id=s['filial'])[0] == 404
    assert requisitar(api, conferir, criar_recepcao(pg, s), filial_id=s['filial'])[0] == 403

    recurso = f'{rota}/{ident}'
    assert requisitar(api, recurso, s['admin'], filial_id=s['second'])[0] == 404
    assert requisitar(api, recurso, s['other'], filial_id=s['filial'])[0] == 403
    assert requisitar(api, recurso, s['user'], method='DELETE', filial_id=s['filial'])[0] == 204
    removido = requisitar(api, recurso, s['user'], filial_id=s['filial'])
    assert removido[0] == 200 and removido[1]['revogado_em']
    assert requisitar(api, recurso, s['admin'], method='DELETE', filial_id=s['filial'])[0] == 204
    assert requisitar(api, recurso, s['user'], filial_id=s['filial']) == removido
    assert chamar(api, rota, method='POST', dados=dados, token=token, cabecalhos=cabecalhos) == (201, removido[1])
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM bloqueios_agenda')) == 1
        assert conn.scalar(text('SELECT revogado_por FROM bloqueios_agenda')) == s['user']


@pytest.mark.parametrize('primeiro', ['reserva', 'bloqueio'])
def test_bloqueio_e_agendamento_concorrentes_nao_coexistem(runtime_pg, duas_filiais, primeiro):
    from app.models import Usuario, Agendamento, BloqueioAgenda, Comanda
    from app.schemas.complementos_agenda import BloqueioCreate
    from app.services import agendamento, bloqueios_agenda
    s = duas_filiais

    def reservar(db):
        return agendamento.criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['admin']))

    def bloquear(db):
        return bloqueios_agenda.criar(db, db.get(Usuario, s['admin']), BloqueioCreate(**bloqueio(s)))

    ordem = (reservar, bloquear) if primeiro == 'reserva' else (bloquear, reservar)
    assert corrida(runtime_pg, *ordem) == 'ConflitoPersistencia'
    with Session(runtime_pg) as db:
        assert db.query(Agendamento).count() == db.query(Comanda).count() == int(primeiro == 'reserva')
        assert db.query(BloqueioAgenda).count() == int(primeiro == 'bloqueio')


def test_ampliacao_da_duracao_valida_conflitos_e_audita_sem_alterar_valores(api, runtime_pg, duas_filiais):
    from app.models import Agendamento, Comanda, Reagendamento
    s = duas_filiais
    entrada = payload(s, s['filial']).model_dump(mode='json') | {'duracao_min': 45}
    codigo, reserva = requisitar(api, '/agendamentos', s['admin'], method='POST', dados=entrada)
    assert codigo == 201 and reserva['hora_fim'] == '09:45:00', reserva
    assert requisitar(api, '/agendamentos/bloqueios', s['admin'], method='POST', dados=bloqueio(s))[0] == 409
    assert requisitar(api, '/agendamentos/bloqueios', s['admin'], method='POST',
                      dados=bloqueio(s, inicio='10:00', fim='10:30'))[0] == 201
    path = f"/agendamentos/{reserva['id']}/reagendamento"
    pedido = dict(data=entrada['data'], hora_inicio=entrada['hora_inicio'], barbeiro_id=entrada['barbeiro_id'],
                  atualizado_em_esperado=reserva['atualizado_em'])
    assert requisitar(api, path, s['admin'], method='PATCH', dados=pedido | {'duracao_min': 70})[0] == 409
    code, edicao = requisitar(api, path, s['admin'], method='PATCH', dados=pedido | {'duracao_min': 60})
    assert code == 200 and edicao['hora_fim'] == '10:00:00', edicao
    with Session(runtime_pg) as db:
        registro = db.scalar(select(Agendamento))
        comanda = db.scalar(select(Comanda))
        historico = db.scalar(select(Reagendamento))
        assert registro.servicos[0].tempo_estimado == 30
        assert comanda.valor_total == 30 and comanda.agendamento_id == registro.id
        assert (historico.hora_fim_anterior, historico.hora_fim_nova) == (time(9, 45), time(10))


def test_encaixe_tem_horario_servidor_e_reaproveita_comanda(api, pg, runtime_pg, agenda, duas_filiais, monkeypatch):
    from app.models import Agendamento, Comanda, PagamentoComanda
    from app.services import agendamento
    s = duas_filiais
    recepcao = criar_recepcao(pg, s)
    dia = date(2099, 5, 20)
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime.combine(dia, time(9), agendamento.FUSO_BARBEARIA))
    caminho = f"/filiais/{s['filial']}/antecedencia"
    politica = dict(antecedencia_reserva_horas=2, antecedencia_maxima_reserva_dias=1, antecedencia_cancelamento_horas=1)
    assert requisitar(api, caminho, s['admin'], method='PUT', dados=politica)[0] == 200
    dados = payload(s, s['filial']).model_dump(mode='json', exclude={'data', 'hora_inicio'}) | {'duracao_min': 40}
    path = '/agendamentos/encaixes'
    assert requisitar(api, path, s['user'], method='POST', dados=dados)[0] == 403
    codigo, reserva = requisitar(api, path, recepcao, method='POST', dados=dados)
    assert codigo == 201, reserva
    assert (reserva['data'], reserva['hora_inicio'], reserva['hora_fim'], reserva['status'], reserva['origem']) == (
        str(dia), '09:00:00', '09:40:00', 'em_atendimento', 'encaixe',
    )
    assert requisitar(api, path, recepcao, method='POST', dados=dados)[0] == 409
    monkeypatch.setattr(agendamento, 'agora_local', lambda: datetime.combine(dia, time(17, 40), agendamento.FUSO_BARBEARIA))
    assert requisitar(api, path, recepcao, method='POST', dados=dados)[0] == 422
    with Session(runtime_pg) as db:
        a = db.scalar(select(Agendamento))
        c = db.scalar(select(Comanda))
        assert c.agendamento_id == a.id and c.status == 'aberta' and c.data_abertura is not None
        assert c.controle_financeiro is not None and c.valor_total == 30
        assert db.query(PagamentoComanda).count() == 0


@pytest.mark.parametrize('perfil', ['admin', 'recepcao', 'user'])
def test_antecedencia_do_portal_nao_limita_agenda_interna(api, pg, duas_filiais, monkeypatch, perfil):
    from app.services import agendamento

    s = duas_filiais
    ator = criar_recepcao(pg, s) if perfil == 'recepcao' else s[perfil]
    dia = date(2099, 5, 20)
    monkeypatch.setattr(agendamento, 'agora_local',
                        lambda: datetime.combine(dia, time(9), agendamento.FUSO_BARBEARIA))
    regras = dict(antecedencia_reserva_horas=2, antecedencia_maxima_reserva_dias=1,
                  antecedencia_cancelamento_horas=1)
    config = f"/filiais/{s['filial']}/antecedencia"
    assert requisitar(api, config, s['admin'], method='PUT', dados=regras)[0] == 200

    entrada = payload(s, s['filial']).model_dump(mode='json', exclude_none=True) | {
        'data': str(dia), 'hora_inicio': '09:00',
    }
    assert requisitar(api, '/agendamentos', ator, method='POST', dados=entrada | {'hora_inicio': '08:59'})[0] == 422
    codigo, reserva = requisitar(api, '/agendamentos', ator, method='POST', dados=entrada)
    assert codigo == 201, reserva

    base = f"/agendamentos/{reserva['id']}"
    remarcacao = dict(barbeiro_id=str(s['user']), motivo='Mudança solicitada',
                      atualizado_em_esperado=reserva['atualizado_em'])
    codigo, distante = requisitar(api, f'{base}/reagendamento', ator, method='PATCH',
                                 dados=remarcacao | {'data': '2099-05-23', 'hora_inicio': '09:00'})
    assert codigo == 200, distante
    codigo, proxima = requisitar(api, f'{base}/reagendamento', ator, method='PATCH',
                                dados=remarcacao | {'data': str(dia), 'hora_inicio': '09:30',
                                                    'atualizado_em_esperado': distante['atualizado_em']})
    assert codigo == 200, proxima
    codigo, cancelada = requisitar(api, f'{base}/status', ator, method='PATCH', dados=dict(
        status='cancelado', confirmado=True, motivo_cancelamento='Mudança solicitada',
        atualizado_em_esperado=proxima['atualizado_em'],
    ))
    assert codigo == 200 and cancelada['status'] == 'cancelado'


def test_migracao_concede_update_colunar_da_politica(pg):
    with pg.connect() as db:
        for coluna in ('antecedencia_reserva_horas', 'antecedencia_maxima_reserva_dias', 'antecedencia_cancelamento_horas'):
            assert db.scalar(text(
                "SELECT has_column_privilege('relaxabarber_dev_app','public.filiais',:coluna,'UPDATE')"
            ), {'coluna': coluna})


def test_antecedencia_por_filial_filtra_e_revalida_sem_mover_reserva(api, pg, runtime_pg, agenda, duas_filiais, monkeypatch):
    from app.services import agendamento, minha_agenda, reserva_publica
    from datetime import timedelta
    from types import SimpleNamespace
    from app.services.errors import ConflitoEstadoAgendamento, HorarioAgendamentoInvalido
    s = duas_filiais
    recepcao = criar_recepcao(pg, s)
    dia = date(2099, 5, 20)
    agora = datetime.combine(dia, time(9), agendamento.FUSO_BARBEARIA)
    monkeypatch.setattr(agendamento, 'agora_local', lambda: agora)
    entrada = payload(s, s['filial']).model_dump(mode='json') | {'data': str(dia), 'hora_inicio': '09:30:00'}
    code, reserva = requisitar(api, '/agendamentos', s['admin'], method='POST', dados=entrada)
    assert code == 201, reserva
    config = f"/filiais/{s['filial']}/antecedencia"
    regras = dict(antecedencia_reserva_horas=1, antecedencia_maxima_reserva_dias=2, antecedencia_cancelamento_horas=1)
    assert requisitar(api, config, s['user'], method='PUT', dados=regras)[0] == 403
    assert requisitar(api, config, s['admin'], method='PUT', dados=regras | {'antecedencia_reserva_horas': -1})[0] == 422
    for invalidas in ({'antecedencia_maxima_reserva_dias': 0}, {'antecedencia_reserva_horas': 48},
                     {'antecedencia_cancelamento_horas': 87601}):
        assert requisitar(api, config, s['admin'], method='PUT', dados=regras | invalidas)[0] == 422
    longa = regras | {'antecedencia_reserva_horas': 192, 'antecedencia_maxima_reserva_dias': 30}
    assert requisitar(api, config, s['admin'], method='PUT', dados=longa) == (200, longa)
    assert requisitar(api, config, s['admin'], method='PUT', dados=regras) == (200, regras)
    assert requisitar(api, f"/filiais/{s['second']}/antecedencia", s['admin'])[1] == (dict.fromkeys(regras, 0) | {'antecedencia_maxima_reserva_dias': None})
    with Session(runtime_pg) as db:
        resultado = reserva_publica.listar_horarios(db, s['service'], dia, s['other'], s['filial'])
        assert resultado['horarios'][0] == '10:00'
        pedido = pedido_publico(agenda, filial_id=s['filial'], data=dia, hora_inicio=time(9, 45), barbeiro_id=s['other'])
        with pytest.raises(HorarioAgendamentoInvalido, match='1 h'):
            reserva_publica.confirmar(db, pedido, agenda['token'])
        atuais = minha_agenda.listar(db, agenda['token'])
        atual = next(a for a in atuais if str(a.id) == reserva['id'])
        assert atual.hora_inicio == time(9, 30) and not atual.pode_cancelar
        limite = dia + timedelta(days=2)
        distante = limite + timedelta(days=1)
        assert reserva_publica.listar_horarios(db, s['service'], limite, s['other'], s['filial'])['horarios'][-1] == '09:00'
        assert reserva_publica.listar_horarios(db, s['service'], distante, s['other'], s['filial'])['horarios'] == []
        longe = pedido_publico(agenda, filial_id=s['filial'], data=distante, hora_inicio=time(10), barbeiro_id=s['other'])
        with pytest.raises(HorarioAgendamentoInvalido, match='2 dias'):
            reserva_publica.confirmar(db, longe, agenda['token'])
        assert minha_agenda.opcoes(db, agenda['token'], atual.id, distante)['horarios'] == []
        assert minha_agenda.opcoes(db, agenda['token'], atual.id, dia)['horarios'][0] == '10:00'
        with pytest.raises(HorarioAgendamentoInvalido, match='1 h'):
            minha_agenda.remarcar(db, agenda['token'], atual.id, SimpleNamespace(
                data=dia, hora_inicio=time(9, 45), atualizado_em_esperado=atual.atualizado_em,
            ))
        with pytest.raises(HorarioAgendamentoInvalido, match='2 dias'):
            minha_agenda.remarcar(db, agenda['token'], atual.id, SimpleNamespace(
                data=distante, hora_inicio=time(10), atualizado_em_esperado=atual.atualizado_em,
            ))
        with pytest.raises(ConflitoEstadoAgendamento, match='1 h'):
            minha_agenda.cancelar(db, agenda['token'], atual.id, SimpleNamespace(
                atualizado_em_esperado=atual.atualizado_em,
            ))
    assert requisitar(api, '/agendamentos', s['admin'], method='POST',
                     dados=entrada | {'hora_inicio': '09:45:00', 'barbeiro_id': str(s['other'])})[0] == 201
    cancelamento = dict(status='cancelado', motivo_cancelamento='Motivo', confirmado=True, atualizado_em_esperado=reserva['atualizado_em'])
    path = f"/agendamentos/{reserva['id']}/status"
    code, resultado = requisitar(api, path, recepcao, method='PATCH', dados=cancelamento, filial_id=s['filial'])
    assert code == 200 and resultado['status'] == 'cancelado'
    code, atual = requisitar(api, f"/agendamentos/{reserva['id']}", s['admin'], filial_id=s['filial'])
    assert code == 200 and atual['status'] == 'cancelado' and atual['hora_inicio'] == '09:30:00'
