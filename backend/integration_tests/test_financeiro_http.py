"""API completa, JWT real e serviços reais no PostgreSQL descartável restrito."""
from datetime import datetime, timedelta, timezone
import importlib
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso
from test_seguranca_horarios import chamar


@pytest.fixture
def api(runtime_pg):
    from app.db.database import get_db
    app = importlib.import_module('app.main').app
    def sessao():
        with Session(runtime_pg, autoflush=False) as db:
            yield db
    app.dependency_overrides[get_db] = sessao
    yield app
    app.dependency_overrides.clear()


def requisitar(api, s, suffix='financeiro', *, perfil='recepcao', body=None, key=None,
               token=None, comanda=None, query=''):
    from app.core.security import criar_token
    if token is None:
        token = criar_token(s['atores'][perfil])
    async def com_header(scope, receive, send):
        if key is not None:
            scope = dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(key).encode())])
        await api(scope, receive, send)
    return chamar(com_header, f"/comandas/{comanda or s['comanda']}/{suffix}{query}",
        method='GET' if suffix == 'financeiro' else 'POST', dados=body, token=token)


def pagamento(**changes):
    return dict(valor='10.00', forma='pix',
        recebido_em=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()) | changes


def pagar(api, s, *, perfil='recepcao', key=None, **changes):
    return requisitar(api, s, 'pagamentos', perfil=perfil, body=pagamento(**changes), key=key or uuid4())


def erro(response, status, codigo):
    assert response[0] == status, response
    assert response[1]['detail']['codigo'] == codigo, response


def contagens(pg):
    with pg.connect() as conn:
        return tuple(conn.scalar(text(f'SELECT count(*) FROM {t}')) for t in (
            'pagamentos_comanda', 'estornos_pagamento', 'fechamentos_financeiros_comanda'))


@pytest.mark.parametrize('perfil', ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_perfis_proprias_parcial_integral_e_fechamento(api, pg, caso, perfil):
    if perfil == 'barbeiro_chefe':
        with pg.begin() as conn:
            conn.execute(text("UPDATE usuarios SET perfil='BARBEIRO_CHEFE' WHERE id=:user"), caso)
        caso['atores'][perfil] = caso['user']
    status, resumo = requisitar(api, caso, perfil=perfil)
    assert status == 200 and resumo['saldo'] == resumo['total'] == '30.50'
    assert pagar(api, caso, perfil=perfil, valor='10.01')[0] == 200
    resumo = requisitar(api, caso, perfil=perfil)[1]
    assert resumo['pagamentos'] == resumo['recebido_liquido'] == '10.01' and resumo['saldo'] == '20.49'
    erro(pagar(api, caso, perfil=perfil, valor='20.50'), 409, 'saldo_insuficiente')
    assert pagar(api, caso, perfil=perfil, valor='20.49', forma='credito')[0] == 200
    assert requisitar(api, caso, perfil=perfil)[1]['situacao'] == 'aberto'
    key = uuid4()
    resultado = requisitar(api, caso, 'fechamento-financeiro', perfil=perfil, body={}, key=key)
    assert resultado[0] == 200 and resultado[1]['total'] == resultado[1]['recebido_liquido'] == '30.50'
    assert requisitar(api, caso, 'fechamento-financeiro', perfil=perfil, body={}, key=key) == resultado
    erro(requisitar(api, caso, 'fechamento-financeiro', perfil=perfil, body={'motivo': 'Outro'}, key=key),
         409, 'conflito_idempotencia')
    erro(requisitar(api, caso, 'fechamento-financeiro', perfil=perfil, body={}, key=uuid4()),
         409, 'estado_financeiro_incompativel')
    erro(pagar(api, caso, perfil=perfil, valor='0.01'), 409, 'estado_financeiro_incompativel')
    assert requisitar(api, caso, perfil=perfil)[1]['situacao'] == 'fechado'
    assert contagens(pg) == (2, 0, 1)
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT status FROM comandas')) == 'fechada'
        assert conn.scalar(text('SELECT status FROM agendamentos')) == 'concluido'


@pytest.mark.parametrize('perfil', ['barbeiro', 'barbeiro_chefe'])
@pytest.mark.parametrize('suffix', ['financeiro', 'pagamentos', 'fechamento-financeiro'])
def test_outro_profissional_404_uniforme(api, pg, caso, perfil, suffix):
    if perfil == 'barbeiro':
        perfil = 'outro'
    args = dict(perfil=perfil, body=pagamento() if suffix == 'pagamentos' else {}, key=uuid4())
    real = requisitar(api, caso, suffix, **args)
    inexistente = requisitar(api, caso, suffix, comanda=uuid4(), **args)
    erro(real, 404, 'comanda_financeira_nao_encontrada')
    assert real == inexistente
    assert str(caso['comanda']) not in str(real) and '30.50' not in str(real)
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize('suffix', ['financeiro', 'pagamentos', 'estornos', 'fechamento-financeiro'])
def test_filial_query_nao_transfere_recurso(api, pg, caso, suffix):
    body = pagamento() if suffix == 'pagamentos' else (
        dict(pagamento_id=str(uuid4()), valor='1', motivo='Correção', efetivado_em=datetime.now(timezone.utc).isoformat())
        if suffix == 'estornos' else {})
    erro(requisitar(api, caso, suffix, perfil='admin', body=body, key=uuid4(),
        query=f"?filial_id={caso['outra_filial']}"), 404, 'comanda_financeira_nao_encontrada')
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize('suffix', ['financeiro', 'pagamentos', 'fechamento-financeiro'])
def test_sem_vinculo_na_filial_da_comanda(api, pg, caso, suffix):
    with pg.begin() as conn:
        conn.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id'),
                     {'id': caso['atores']['recepcao']})
    erro(requisitar(api, caso, suffix, body=pagamento() if suffix == 'pagamentos' else {}, key=uuid4()),
         404, 'comanda_financeira_nao_encontrada')
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize('alvo,status', [('usuario', 401), ('vinculo', 404), ('filial', 404), ('empresa', 404), ('perfil', 404)])
def test_revogacao_com_mesmo_jwt_bloqueia_consulta_e_replay(api, pg, caso, alvo, status):
    from app.core.security import criar_token
    token, key, body = criar_token(caso['atores']['recepcao']), uuid4(), pagamento()
    assert requisitar(api, caso, 'pagamentos', token=token, body=body, key=key)[0] == 200
    with pg.begin() as conn:
        if alvo == 'usuario':
            conn.execute(text('UPDATE usuarios SET ativo=false WHERE id=:id'), {'id': caso['atores']['recepcao']})
        elif alvo == 'vinculo':
            conn.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id'), {'id': caso['atores']['recepcao']})
        elif alvo == 'perfil':
            conn.execute(text("UPDATE usuarios SET perfil='BARBEIRO' WHERE id=:id"), {'id': caso['atores']['recepcao']})
        elif alvo == 'filial':
            conn.execute(text('UPDATE filiais SET ativa=false WHERE id=:filial'), caso)
        else:
            conn.execute(text('UPDATE empresas SET ativa=false'))
    for suffix, args in [('financeiro', {}), ('pagamentos', dict(body=body, key=key))]:
        resultado = requisitar(api, caso, suffix, token=token, **args)
        assert resultado[0] == status and '30.50' not in str(resultado)
    assert contagens(pg) == (1, 0, 0)


def test_pagamento_replay_canonico_conflito_e_apos_fechamento(api, pg, caso):
    key = uuid4()
    instante = datetime.now(timezone.utc) - timedelta(minutes=1)
    body = pagamento(valor='30.5', recebido_em=instante.astimezone(timezone(timedelta(hours=-3))).isoformat())
    primeiro = requisitar(api, caso, 'pagamentos', body=body, key=key)
    assert primeiro[0] == 200 and primeiro[1]['valor'] == '30.50'
    assert primeiro[1]['recebido_em'].endswith('Z') and primeiro[1]['registrado_em'].endswith('Z')
    canonico = body | {'valor': '30.50', 'recebido_em': instante.isoformat()}
    assert requisitar(api, caso, 'pagamentos', body=canonico, key=key) == primeiro
    for change in ({'valor': '30.49'}, {'forma': 'debito'}, {'recebido_em': (instante - timedelta(seconds=1)).isoformat()}):
        erro(requisitar(api, caso, 'pagamentos', body=body | change, key=key), 409, 'conflito_idempotencia')
    assert requisitar(api, caso, 'fechamento-financeiro', body={}, key=uuid4())[0] == 200
    assert requisitar(api, caso, 'pagamentos', body=body, key=key) == primeiro
    assert contagens(pg) == (1, 0, 1)


@pytest.mark.parametrize('confirmado', [False, True])
def test_timeout_confirmacao_e_repeticao_mesma_chave(api, pg, caso, monkeypatch, confirmado):
    from app.services import financeiro as servico
    from app.services.persistencia import ConfirmacaoIndeterminada, BancoIndisponivel
    original = servico.registrar_pagamento
    def resposta_perdida(*args, **kwargs):
        if confirmado:
            original(*args, **kwargs)  # commit real; simula perda da confirmação
            raise ConfirmacaoIndeterminada()
        raise BancoIndisponivel()  # falha antes de qualquer escrita
    key, body = uuid4(), pagamento()
    with monkeypatch.context() as patch:
        patch.setattr(servico, 'registrar_pagamento', resposta_perdida)
        erro(requisitar(api, caso, 'pagamentos', body=body, key=key), 503,
             'confirmacao_indeterminada' if confirmado else 'banco_indisponivel')
    resultado = requisitar(api, caso, 'pagamentos', body=body, key=key)
    assert resultado[0] == 200
    assert requisitar(api, caso, 'pagamentos', body=body, key=key) == resultado
    assert contagens(pg) == (1, 0, 0)


@pytest.mark.parametrize('perfil,idade,status', [
    ('recepcao', timedelta(hours=168), 200),
    ('recepcao', timedelta(hours=168, microseconds=1), 422),
    ('recepcao', timedelta(microseconds=-1), 422),
    ('admin', timedelta(days=365), 200), ('admin', timedelta(microseconds=-1), 422),
])
def test_retroatividade_limite_inclusivo_e_futuro(api, pg, caso, monkeypatch, perfil, idade, status):
    from app.services import financeiro as servico
    agora = datetime(2026, 11, 13, 13, tzinfo=timezone.utc)
    monkeypatch.setattr(servico, '_agora', lambda db: agora)
    resultado = pagar(api, caso, perfil=perfil, recebido_em=(agora - idade).isoformat())
    assert resultado[0] == status
    if status == 422:
        erro(resultado, 422, 'entrada_financeira_invalida')
    assert contagens(pg)[0] == (1 if status == 200 else 0)


@pytest.mark.parametrize('estado,comanda', [('pendente', 'pendente'), ('aguardando', 'aberta'),
    ('em_atendimento', 'aberta'), ('cancelado', 'cancelada'), ('concluido', 'aberta')])
def test_pagamento_e_fechamento_exigem_conclusao_operacional(api, pg, caso, estado, comanda):
    with pg.begin() as conn:
        conn.execute(text('UPDATE agendamentos SET status=:estado'), {'estado': estado})
        conn.execute(text('UPDATE comandas SET status=:estado'), {'estado': comanda})
    erro(pagar(api, caso), 409, 'estado_financeiro_incompativel')
    erro(requisitar(api, caso, 'fechamento-financeiro', body={}, key=uuid4()), 409, 'estado_financeiro_incompativel')
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize('perfil', ['recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_estorno_exclusivo_admin(api, pg, caso, perfil):
    p = pagar(api, caso)[1]
    body = dict(pagamento_id=p['id'], valor='1', motivo='Correção', efetivado_em=datetime.now(timezone.utc).isoformat())
    erro(requisitar(api, caso, 'estornos', perfil=perfil, body=body, key=uuid4()), 403, 'acesso_financeiro_negado')
    assert contagens(pg) == (1, 0, 0)


def test_estorno_admin_replay_conflitos_limites_e_fechamento(api, pg, caso):
    p = pagar(api, caso, valor='30.50')[1]
    key = uuid4()
    body = dict(pagamento_id=p['id'], valor='2.01', motivo='  Correção  ',
                efetivado_em=datetime.now(timezone.utc).isoformat())
    resultado = requisitar(api, caso, 'estornos', perfil='admin', body=body, key=key)
    assert resultado[0] == 200 and resultado[1]['valor'] == '2.01' and resultado[1]['motivo'] == 'Correção'
    assert requisitar(api, caso, 'estornos', perfil='admin', body=body | {'motivo': 'Correção'}, key=key) == resultado
    for change in ({'valor': '2.02'}, {'motivo': 'Outro'}, {'pagamento_id': str(uuid4())}):
        erro(requisitar(api, caso, 'estornos', perfil='admin', body=body | change, key=key), 409, 'conflito_idempotencia')
    erro(requisitar(api, caso, 'estornos', perfil='admin', body=body | {'valor': '28.50'}, key=uuid4()),
         409, 'limite_estorno_excedido')
    erro(requisitar(api, caso, 'estornos', perfil='admin', body=body | {'pagamento_id': str(uuid4())}, key=uuid4()),
         404, 'comanda_financeira_nao_encontrada')
    erro(requisitar(api, caso, 'estornos', perfil='admin', body=body | {'efetivado_em': '2000-01-01T00:00:00Z'}, key=uuid4()),
         422, 'entrada_financeira_invalida')
    assert requisitar(api, caso)[1]['saldo'] == '2.01'
    erro(requisitar(api, caso, 'fechamento-financeiro', body={}, key=uuid4()), 409, 'saldo_insuficiente')
    assert pagar(api, caso, valor='2.01')[0] == 200
    assert requisitar(api, caso, 'fechamento-financeiro', body={}, key=uuid4())[0] == 200
    assert requisitar(api, caso, 'estornos', perfil='admin', body=body, key=key) == resultado
    erro(requisitar(api, caso, 'estornos', perfil='admin', body=body, key=uuid4()), 409, 'estado_financeiro_incompativel')
    assert contagens(pg) == (2, 1, 1)


def test_valor_zero_exige_motivo_e_nenhum_pagamento(api, pg, caso):
    with pg.begin() as conn:
        conn.execute(text('UPDATE itens_comanda SET preco_unitario=0 WHERE comanda_id=:comanda'), caso)
    resumo = requisitar(api, caso)[1]
    assert resumo['situacao'] == 'aberto' and resumo['saldo'] == resumo['total'] == '0.00'
    erro(pagar(api, caso, valor='0.01'), 409, 'saldo_insuficiente')
    erro(requisitar(api, caso, 'fechamento-financeiro', body={}, key=uuid4()), 422, 'entrada_financeira_invalida')
    status, fechamento = requisitar(api, caso, 'fechamento-financeiro', body={'motivo': '  Cortesia  '}, key=uuid4())
    assert status == 200 and fechamento['motivo'] == 'Cortesia' and fechamento['total'] == '0.00'
    assert contagens(pg) == (0, 0, 1)


def test_legado_null_e_operacoes_bloqueadas_ate_para_admin(api, pg, legado):
    s = legado | {'atores': {'barbeiro': legado['user']}}
    # ADMIN é criado só como ator, sem conciliar o legado.
    from app.models import Usuario, PerfilEnum
    with Session(pg) as db:
        u = Usuario(nome='Admin', email='legado-http@example.test', senha_hash='ficticio', perfil=PerfilEnum.ADMIN)
        db.add(u)
        db.commit()
        s['atores']['admin'] = u.id
    status, resumo = requisitar(api, s, perfil='admin')
    assert status == 200 and resumo['situacao'] == 'nao_verificado' and resumo['total'] == '30.50'
    assert all(resumo[campo] is None for campo in ('pagamentos', 'estornos', 'recebido_liquido', 'saldo'))
    for suffix, body in [('pagamentos', pagamento()), ('fechamento-financeiro', {}),
        ('estornos', dict(pagamento_id=str(uuid4()), valor='1', motivo='Correção', efetivado_em=datetime.now(timezone.utc).isoformat()))]:
        erro(requisitar(api, s, suffix, perfil='admin', body=body, key=uuid4()), 409, 'historico_financeiro_nao_verificado')
    assert contagens(pg) == (0, 0, 0)
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM controles_financeiros_comanda')) == 0


def test_consulta_sem_commit_e_escrita_com_um_commit(api, runtime_pg, caso):
    commits = []
    def registrar(conn):
        commits.append(True)
    event.listen(runtime_pg, 'commit', registrar)
    try:
        assert requisitar(api, caso)[0] == 200
        assert not commits
        assert pagar(api, caso)[0] == 200
        assert len(commits) == 1
    finally:
        event.remove(runtime_pg, 'commit', registrar)


def test_estorno_nao_revela_pagamento_real_de_outra_comanda_filial(api, pg, caso):
    from test_financeiro_persistencia import criar_comanda
    from app.models import UsuarioFilial
    # Outra filial possui outra comanda e pagamento reais. ADMIN pode operar
    # ambas, mas não pode vincular um estorno ao contexto errado.
    with Session(pg) as db:
        db.add(UsuarioFilial(usuario_id=caso['user'], filial_id=caso['outra_filial']))
        db.commit()
    with pg.begin() as conn:
        outra = criar_comanda(conn, caso | {'filial': caso['outra_filial']}, dia='2099-02-01', controle=True)
    pagamento_externo = requisitar(api, caso, 'pagamentos', perfil='admin',
        comanda=outra['comanda'], body=pagamento(), key=uuid4())
    assert pagamento_externo[0] == 200
    body = dict(pagamento_id=pagamento_externo[1]['id'], valor='1.00', motivo='Correção',
                efetivado_em=datetime.now(timezone.utc).isoformat())
    real = requisitar(api, caso, 'estornos', perfil='admin', body=body, key=uuid4())
    ausente = requisitar(api, caso, 'estornos', perfil='admin',
        body=body | {'pagamento_id': str(uuid4())}, key=uuid4())
    erro(real, 404, 'comanda_financeira_nao_encontrada')
    assert real == ausente and pagamento_externo[1]['id'] not in str(real)
    # RECEPCAO não tem vínculo na outra filial; UUID real e inexistente são iguais.
    assert requisitar(api, caso, comanda=outra['comanda']) == requisitar(api, caso, comanda=uuid4())
    assert contagens(pg) == (1, 0, 0)


def test_revogacao_admin_bloqueia_replay_estorno_e_fechamento(api, pg, caso):
    from app.core.security import criar_token
    token = criar_token(caso['atores']['admin'])
    p = pagar(api, caso, valor='30.50')[1]
    key = uuid4()
    body = dict(pagamento_id=p['id'], valor='1.00', motivo='Correção', efetivado_em=datetime.now(timezone.utc).isoformat())
    assert requisitar(api, caso, 'estornos', token=token, body=body, key=key)[0] == 200
    assert pagar(api, caso, valor='1.00')[0] == 200
    chave_fechamento = uuid4()
    assert requisitar(api, caso, 'fechamento-financeiro', token=token, body={}, key=chave_fechamento)[0] == 200
    with pg.begin() as conn:
        conn.execute(text("UPDATE usuarios SET perfil='BARBEIRO' WHERE id=:id"), {'id': caso['atores']['admin']})
    erro(requisitar(api, caso, 'estornos', token=token, body=body, key=key), 403, 'acesso_financeiro_negado')
    erro(requisitar(api, caso, 'fechamento-financeiro', token=token, body={}, key=chave_fechamento),
         404, 'comanda_financeira_nao_encontrada')
    assert contagens(pg) == (2, 1, 1)
