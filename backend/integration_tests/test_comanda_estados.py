"""Compatibilidade da Etapa 1 no PostgreSQL descartável, inclusive login restrito."""
from decimal import Decimal
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from test_financeiro_persistencia import data, legado, financeiro, pagar as inserir_historico
from test_financeiro_servicos import caso, fechar, disputar


@pytest.mark.parametrize('historica', [False, True])
def test_fechamento_preserva_data_historica_e_fecha_nova(runtime_pg, pg, caso, historica):
    antiga = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with pg.begin() as conn:
        conn.execute(text('UPDATE comandas SET status=:estado, data_fechamento=:data'),
            {'estado': 'fechada' if historica else 'aberta', 'data': antiga if historica else None})
        inserir_historico(conn, caso, valor=Decimal('30.50'))
    with Session(runtime_pg) as db:
        resultado = fechar(db, caso)
    with pg.connect() as conn:
        estado, data = conn.execute(text('SELECT status, data_fechamento FROM comandas')).one()
        assert estado == 'fechada'
        assert data == (antiga if historica else resultado.registrado_em)


def test_fechamentos_nova_comanda_disputam_lock(pg, caso):
    from uuid import uuid4
    with pg.begin() as conn:
        conn.execute(text("UPDATE comandas SET status='aberta', data_fechamento=NULL"))
        inserir_historico(conn, caso, valor=Decimal('30.50'))
    chave = uuid4()
    primeiro, segundo = disputar(pg,
        lambda db: fechar(db, caso, chave_idempotencia=chave),
        lambda db: fechar(db, caso, chave_idempotencia=chave))
    assert primeiro == segundo
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM fechamentos_financeiros_comanda')) == 1
        assert conn.scalar(text('SELECT data_fechamento FROM comandas')) == primeiro.registrado_em
