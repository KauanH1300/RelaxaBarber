"""Operação integral real, exclusivamente no PostgreSQL descartável validado."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4, uuid5

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from test_financeiro_persistencia import data, legado, financeiro
from test_financeiro_servicos import caso, ator, historico, fechar, estornar, contagens, disputar
from test_financeiro_http import api, requisitar, pagamento, erro


def parcelas():
    efetiva = datetime.now(timezone.utc) - timedelta(minutes=1)
    return [dict(valor=Decimal(v), forma=f, recebido_em=efetiva, confirmado=True)
            for v, f in [('10.01', 'pix'), ('20.49', 'debito')]]


@pytest.mark.parametrize('historica', [False, True])
def test_regulariza_liquido_preserva_lancamentos_e_datas(pg, runtime_pg, caso, historica):
    antiga = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with pg.begin() as conn:
        conn.execute(text('UPDATE comandas SET status=:status, data_fechamento=:data'),
            dict(status='fechada' if historica else 'aberta', data=antiga if historica else None))
    with Session(pg) as db:
        p = historico(db, caso, valor=Decimal('15.00'))
        e = estornar(db, caso, p, valor=Decimal('2.00'))
    with pg.connect() as conn:
        antes = conn.execute(text('SELECT to_jsonb(p) FROM pagamentos_comanda p')).scalar()
    with Session(runtime_pg) as db:
        ps = parcelas()
        ps[0]['valor'], ps[1]['valor'] = Decimal('7.00'), Decimal('10.50')
        f = fechar(db, caso, pagamentos=ps)
        assert f.total == f.recebido_liquido == Decimal('30.50')
    with pg.connect() as conn:
        assert conn.execute(text('SELECT to_jsonb(p) FROM pagamentos_comanda p WHERE id=:id'), dict(id=p.id)).scalar() == antes
        assert conn.scalar(text('SELECT id FROM estornos_pagamento')) == e.id
        assert conn.scalar(text('SELECT data_fechamento FROM comandas')) == (antiga if historica else f.registrado_em)
    assert contagens(pg) == (3, 1, 1)


@pytest.mark.parametrize('falha', ['segundo_pagamento', 'fechamento', 'estado', 'commit'])
def test_rollback_integral_inclusive_estado(pg, runtime_pg, caso, falha):
    with pg.begin() as conn:
        conn.execute(text("UPDATE comandas SET status='aberta', data_fechamento=NULL"))
    vistos = []
    def interceptar(conn, cursor, sql, params, context, executemany):
        if sql.startswith('INSERT INTO pagamentos_comanda'):
            vistos.append(sql)
            if falha == 'segundo_pagamento' and len(vistos) == 2:
                raise RuntimeError('Falha injetada')
        if falha == 'fechamento' and sql.startswith('INSERT INTO fechamentos_financeiros_comanda'):
            raise RuntimeError('Falha injetada')
        if falha == 'estado' and sql.startswith('UPDATE comandas'):
            raise RuntimeError('Falha injetada')
    def falhar_commit(db):
        db.flush()
        raise RuntimeError('Falha após flush integral')
    event.listen(runtime_pg, 'before_cursor_execute', interceptar)
    try:
        with Session(runtime_pg) as db:
            if falha == 'commit':
                event.listen(db, 'before_commit', falhar_commit)
            with pytest.raises(RuntimeError):
                fechar(db, caso, pagamentos=parcelas())
            assert db.scalar(text('SELECT 1')) == 1
    finally:
        event.remove(runtime_pg, 'before_cursor_execute', interceptar)
    assert vistos and contagens(pg) == (0, 0, 0)
    with pg.connect() as conn:
        assert conn.execute(text('SELECT status,data_fechamento FROM comandas')).one() == ('aberta', None)


@pytest.mark.parametrize('confirmar', [False, True])
def test_timeout_da_operacao_inteira_e_replay(pg, caso, confirmar):
    from app.services.persistencia import ConfirmacaoIndeterminada
    ps, chave = parcelas(), uuid4()
    class Incerta(Session):
        def commit(self):
            if confirmar:
                super().commit()
            raise OperationalError(None, {}, SimpleNamespace(pgcode='08006'), connection_invalidated=True)
    with Incerta(pg) as db:
        with pytest.raises(ConfirmacaoIndeterminada):
            fechar(db, caso, pagamentos=ps, chave_idempotencia=chave)
    assert contagens(pg) == (2*int(confirmar), 0, int(confirmar))
    with Session(pg) as db:
        f = fechar(db, caso, pagamentos=ps, chave_idempotencia=chave)
        assert fechar(db, caso, pagamentos=ps, chave_idempotencia=chave) == f
    assert contagens(pg) == (2, 0, 1)


@pytest.mark.parametrize('modo', ['mesma_chave', 'outra_chave', 'payload_diferente'])
def test_multiplos_metodos_concorrentes_uma_operacao(pg, caso, modo):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel, ConflitoIdempotenciaFinanceira
    ps, chave = parcelas(), uuid4()
    segundo = [p.copy() for p in ps]
    if modo == 'payload_diferente':
        segundo[0]['forma'] = 'dinheiro'
    um, dois = disputar(pg,
        lambda db: fechar(db, caso, pagamentos=ps, chave_idempotencia=chave),
        lambda db: fechar(db, caso, pagamentos=segundo, chave_idempotencia=uuid4() if modo == 'outra_chave' else chave))
    if modo == 'mesma_chave':
        assert um == dois
    else:
        assert isinstance(dois, EstadoFinanceiroIncompativel if modo == 'outra_chave' else ConflitoIdempotenciaFinanceira)
    assert contagens(pg) == (2, 0, 1)


@pytest.mark.parametrize('mudanca', [
    {'valor':'0'}, {'valor':'-1'}, {'valor':1.0}, {'valor':'NaN'}, {'valor':'1.001'},
    {'valor':'100000000.00'}, {'forma':'fiado'}, {'forma':'credito_loja'},
    {'confirmado':False}, {'confirmado':None}, {'confirmado':'true'}, {'confirmado':1},
    {'recebido_em':'2026-11-13T10:00:00'}, {'saldo':'0'},
])
def test_http_rejeita_parcela_invalida_sem_efeitos(api, pg, caso, mudanca):
    body = {'pagamentos':[pagamento(valor='30.50') | {'confirmado':True} | mudanca]}
    assert requisitar(api, caso, 'fechamento-financeiro', body=body, key=uuid4())[0] == 422
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize('body', [
    {'pagamentos':[pagamento(valor='30.50')]},
    {'pagamentos':None}, {'pagamentos':[pagamento(valor='1') | {'confirmado':True}]*17},
])
def test_http_exige_confirmacao_e_limita_lista(api, pg, caso, body):
    assert requisitar(api, caso, 'fechamento-financeiro', body=body, key=uuid4())[0] == 422
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize('valor', ['10.00','30.50'])
def test_endpoint_antigo_nao_cria_nenhum_pagamento(api, pg, caso, valor):
    erro(requisitar(api, caso, 'pagamentos', body=pagamento(valor=valor), key=uuid4()),
         409, 'estado_financeiro_incompativel')
    assert contagens(pg) == (0,0,0)


def test_quitada_fecha_sem_cobrar_e_replay_historico_permanece(api, pg, caso):
    body, chave = pagamento(valor='30.50'), uuid4()
    from test_financeiro_http import preparar_pagamento
    preparar_pagamento(pg, caso, key=chave, **body)
    primeiro = requisitar(api, caso, 'pagamentos', body=body, key=chave)
    assert primeiro[0] == 200
    fechamento = uuid4()
    f = requisitar(api, caso, 'fechamento-financeiro', body={}, key=fechamento)
    assert f[0] == 200
    assert requisitar(api, caso, 'fechamento-financeiro', body={}, key=fechamento) == f
    assert requisitar(api, caso, 'pagamentos', body=body, key=chave) == primeiro
    assert contagens(pg) == (1,0,1)


def test_colisao_com_chave_historica_reverte_integralmente(pg, caso):
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira
    chave = uuid4()
    with Session(pg) as db:
        historico(db, caso, valor=Decimal('1'), chave_idempotencia=uuid5(chave,f"{caso['comanda']}:1"))
        ps = parcelas()
        ps[1]['valor'] -= Decimal('1')
        with pytest.raises(ConflitoIdempotenciaFinanceira):
            fechar(db, caso, pagamentos=ps, chave_idempotencia=chave)
    assert contagens(pg) == (1,0,0)


def test_estorno_novo_bloqueado_imediatamente_apos_integral(pg, caso):
    from app.models import PagamentoComanda
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with Session(pg) as db:
        fechar(db, caso, pagamentos=parcelas())
        p = db.scalar(select(PagamentoComanda))
        with pytest.raises(EstadoFinanceiroIncompativel):
            estornar(db, caso, p)
    assert contagens(pg) == (2,0,1)
