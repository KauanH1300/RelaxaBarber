"""Histórico HTTP persistido: PostgreSQL descartável, login runtime e JWT reais."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text

from test_financeiro_http import api, requisitar, pagar, pagamento, erro, contagens, preparar_pagamento
from test_financeiro_servicos import caso
from test_financeiro_persistencia import data, legado, financeiro, criar_comanda, pagar as inserir_pagamento


def estornar(api, s, pagamento_id, valor='1.00'):
    return requisitar(api, s, 'estornos', perfil='admin', key=uuid4(), body={
        'pagamento_id': pagamento_id, 'valor': valor, 'motivo': 'Correção de recebimento',
        'efetivado_em': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    })


@pytest.mark.parametrize('perfil', ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_historico_persistido_reabertura_multiplos_pagamentos_estornos_e_fechamento(api, pg, caso, perfil):
    if perfil == 'barbeiro_chefe':
        with pg.begin() as conn:
            conn.execute(text("UPDATE usuarios SET perfil='BARBEIRO_CHEFE' WHERE id=:user"), caso)
        caso['atores'][perfil] = caso['user']
    p1 = preparar_pagamento(pg, caso, valor='10.50', forma='dinheiro')[1]
    p2 = preparar_pagamento(pg, caso, valor='20.00', forma='pix')[1]
    assert estornar(api, caso, p1['id'], '2.00')[0] == 200
    assert estornar(api, caso, p1['id'], '1.50')[0] == 200
    # Cada requisição abre outra sessão PostgreSQL: não depende de memória local.
    status, resumo = requisitar(api, caso, perfil=perfil)
    assert status == 200
    assert (resumo['pagamentos'], resumo['estornos'], resumo['recebido_liquido'], resumo['saldo']) == ('30.50', '3.50', '27.00', '3.50')
    historico = resumo['historico']
    assert {p['id'] for p in historico['pagamentos']} == {p1['id'], p2['id']}
    assert sum(Decimal(e['valor']) for e in historico['estornos']) == Decimal('3.50')
    assert all(e['pagamento_id'] == p1['id'] for e in historico['estornos'])
    assert requisitar(api, caso, perfil=perfil)[1] == resumo
    assert pagar(api, caso, valor='3.50', forma='credito')[0] == 200
    fechado = requisitar(api, caso, perfil=perfil)[1]
    assert fechado['situacao'] == 'fechado' and fechado['saldo'] == '0.00'
    assert len(fechado['historico']['pagamentos']) == 3 and len(fechado['historico']['estornos']) == 2
    assert requisitar(api, caso, perfil=perfil)[1] == fechado
    erro(estornar(api, caso, p2['id']), 409, 'estado_financeiro_incompativel')
    assert contagens(pg) == (3, 2, 1)


def test_ordenacao_deterministica_por_registro_e_uuid_com_empates(api, pg, caso):
    instante = datetime(2026, 1, 2, tzinfo=timezone.utc)
    ids = [UUID(int=i) for i in (30, 10, 20)]
    with pg.begin() as conn:
        # Apenas na preparação do banco descartável: o trigger substitui datas
        # por clock_timestamp(), portanto o empate exato precisa de fixture controlada.
        for tabela in ('pagamentos_comanda', 'estornos_pagamento'):
            conn.execute(text(f'ALTER TABLE {tabela} DISABLE TRIGGER financeiro_carimbo'))
        for ident in ids:
            inserir_pagamento(conn, caso, id=ident, valor=Decimal('5.00'), registro=instante)
        # Timestamps de registro e efetivos empatados, inserção propositalmente invertida.
        for ident in (UUID(int=90), UUID(int=80)):
            conn.execute(text('''INSERT INTO estornos_pagamento
                (id,pagamento_id,comanda_id,filial_id,valor,motivo,efetivado_em,registrado_em,registrado_por,chave_idempotencia,fingerprint)
                VALUES (:id,:pagamento,:comanda,:filial,1,'Correção',:instante,:instante,:user,:chave,:fp)'''),
                caso | dict(id=ident, pagamento=ids[0], instante=instante, chave=uuid4(), fp='a' * 64))
        for tabela in ('pagamentos_comanda', 'estornos_pagamento'):
            conn.execute(text(f'ALTER TABLE {tabela} ENABLE TRIGGER financeiro_carimbo'))
    for _ in range(2):
        historico = requisitar(api, caso)[1]['historico']
        assert [p['id'] for p in historico['pagamentos']] == [str(UUID(int=i)) for i in (10, 20, 30)]
        assert [e['id'] for e in historico['estornos']] == [str(UUID(int=i)) for i in (80, 90)]


@pytest.mark.parametrize('perfil', ['outro', 'barbeiro_chefe'])
def test_historico_de_outro_profissional_nao_vaza(api, pg, caso, perfil):
    assert preparar_pagamento(pg, caso)[0] == 200
    real = requisitar(api, caso, perfil=perfil)
    assert real == requisitar(api, caso, perfil=perfil, comanda=uuid4())
    erro(real, 404, 'comanda_financeira_nao_encontrada')
    assert 'historico' not in real[1] and '10.00' not in str(real)


@pytest.mark.parametrize('alvo', ['vinculo', 'filial', 'empresa', 'inativo'])
def test_historico_revalida_escopo_com_dados_persistidos(api, pg, caso, alvo):
    from app.core.security import criar_token
    token = criar_token(caso['atores']['recepcao'])
    assert preparar_pagamento(pg, caso)[0] == 200
    with pg.begin() as conn:
        if alvo == 'vinculo':
            conn.execute(text('UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id'), {'id': caso['atores']['recepcao']})
        elif alvo == 'filial':
            conn.execute(text('UPDATE filiais SET ativa=false WHERE id=:filial'), caso)
        elif alvo == 'empresa':
            conn.execute(text('UPDATE empresas SET ativa=false'))
        else:
            conn.execute(text('UPDATE usuarios SET ativo=false WHERE id=:id'), {'id': caso['atores']['recepcao']})
    resposta = requisitar(api, caso, token=token)
    assert resposta[0] == (401 if alvo == 'inativo' else 404)
    assert 'historico' not in resposta[1] and '10.00' not in str(resposta)


def test_isolamento_entre_comandas_e_filial_query(api, pg, caso):
    p = preparar_pagamento(pg, caso)[1]
    with pg.begin() as conn:
        outra = criar_comanda(conn, caso, dia='2099-01-02', controle=True)
        externo = inserir_pagamento(conn, outra, valor=Decimal('7.00'))
    historico = requisitar(api, caso)[1]['historico']
    assert [registro['id'] for registro in historico['pagamentos']] == [p['id']]
    assert str(externo['id']) not in str(historico)
    assert requisitar(api, caso, comanda=outra['comanda'])[1]['historico']['pagamentos'][0]['id'] == str(externo['id'])
    erro(requisitar(api, caso, perfil='admin', query=f"?filial_id={caso['outra_filial']}"), 404, 'comanda_financeira_nao_encontrada')


def test_legado_historico_vazio_sem_afirmar_quitacao_ou_divida(api, pg, legado):
    from app.core.security import criar_token
    resposta = requisitar(api, legado, token=criar_token(legado['user']))
    assert resposta[0] == 200
    resumo = resposta[1]
    assert resumo['situacao'] == 'nao_verificado' and resumo['historico'] == {'pagamentos': [], 'estornos': []}
    assert all(resumo[campo] is None for campo in ('saldo', 'pagamentos', 'estornos', 'recebido_liquido'))
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM controles_financeiros_comanda')) == 0


def test_get_historico_sem_commit_flush_ou_sql_de_escrita(api, runtime_pg, pg, caso):
    assert preparar_pagamento(pg, caso)[0] == 200
    consultas, commits = [], []
    def observar(conn, cursor, statement, parameters, context, executemany):
        consultas.append(statement)
    def commit(conn):
        commits.append(True)
    event.listen(runtime_pg, 'before_cursor_execute', observar)
    event.listen(runtime_pg, 'commit', commit)
    try:
        assert requisitar(api, caso)[0] == 200
    finally:
        event.remove(runtime_pg, 'before_cursor_execute', observar)
        event.remove(runtime_pg, 'commit', commit)
    assert not commits
    assert consultas and all(sql.lstrip().upper().startswith('SELECT') for sql in consultas)
    assert contagens(pg) == (1, 0, 0)


def test_historico_apos_confirmacao_indeterminada_replay_nao_duplica(api, pg, caso, monkeypatch):
    from app.services import financeiro as servico
    from app.services.persistencia import ConfirmacaoIndeterminada
    original = servico.fechar_comanda
    def perder_resposta(*args, **kwargs):
        original(*args, **kwargs)
        raise ConfirmacaoIndeterminada()
    chave, body = uuid4(), {'pagamentos': [pagamento(valor='30.50') | {'confirmado': True}]}
    with monkeypatch.context() as patch:
        patch.setattr(servico, 'fechar_comanda', perder_resposta)
        erro(requisitar(api, caso, 'fechamento-financeiro', key=chave, body=body), 503, 'confirmacao_indeterminada')
    antes = requisitar(api, caso)[1]
    assert len(antes['historico']['pagamentos']) == 1
    assert requisitar(api, caso, 'fechamento-financeiro', key=chave, body=body)[0] == 200
    assert requisitar(api, caso)[1] == antes and contagens(pg) == (1, 0, 1)
