"""Inclusão real, auditoria, replay, HTTP e disputa com fechamento no PG isolado."""
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError, DBAPIError
from sqlalchemy.orm import Session
from test_financeiro_persistencia import data, legado, financeiro, criar_comanda
from test_financeiro_servicos import caso, ator, fechar, disputar
from test_financeiro_http import api, requisitar
from test_fechamento_integral import parcelas


@pytest.fixture
def aberta(pg, caso):
    with pg.begin() as conn:
        conn.execute(text("UPDATE comandas SET status='aberta',data_fechamento=NULL"))
    return caso


def incluir(db, s, **changes):
    from app.services.itens_comanda import adicionar_servico
    perfil = changes.pop('perfil', 'recepcao')
    args = dict(servico_id=s['service'], quantidade=2, chave_idempotencia=uuid4(), filial_id=s['filial']) | changes
    return adicionar_servico(s['comanda'], db=db, usuario=ator(db, s, perfil), **args)


def test_preco_snapshot_total_auditoria_replay(pg, runtime_pg, aberta):
    s, key = aberta, uuid4()
    with pg.connect() as conn:
        before = conn.scalar(text('SELECT to_jsonb(a) FROM agendamentos a'))
    with Session(runtime_pg) as db:
        r = incluir(db, s, chave_idempotencia=key)
        assert r.total == Decimal('90.50') and r.item.preco_unitario == Decimal('30.00')
        assert r.item.subtotal == Decimal('60.00') and r.item.descricao == 'Corte'
    with pg.begin() as conn:
        conn.execute(text("UPDATE servicos SET preco=99,nome='Novo',ativo=false"))
    with Session(runtime_pg) as db:
        assert incluir(db, s, chave_idempotencia=key) == r
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT to_jsonb(a) FROM agendamentos a')) == before
        assert conn.scalar(text('SELECT count(*) FROM itens_comanda')) == 2
        assert conn.scalar(text('SELECT count(*) FROM inclusoes_servicos_comanda')) == 1
        assert conn.scalar(text("SELECT preco_unitario FROM itens_comanda WHERE descricao='Item ficticio'")) == Decimal('30.50')
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira
    with Session(runtime_pg) as db, pytest.raises(ConflitoIdempotenciaFinanceira):
        incluir(db, s, chave_idempotencia=key, quantidade=1)


@pytest.mark.parametrize('perfil', ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_http_perfis_proprios_payload_somente_catalogo(api, pg, aberta, perfil):
    s = aberta
    if perfil == 'barbeiro_chefe':
        with pg.begin() as conn:
            conn.execute(text("UPDATE usuarios SET perfil='BARBEIRO_CHEFE' WHERE id=:user"), s)
        s['atores'][perfil] = s['user']
    body = dict(servico_id=str(s['service']), quantidade=1)
    key = uuid4()
    r = requisitar(api, s, 'itens/servicos', perfil=perfil, body=body, key=key)
    assert r[0] == 200, r
    assert r[1]['total'] == '60.50'
    assert requisitar(api, s, 'itens/servicos', perfil=perfil, body=body, key=key) == r
    assert requisitar(api, s, 'itens/servicos', perfil=perfil, body=body | {'preco_unitario': 1}, key=uuid4())[0] == 422
    assert requisitar(api, s, 'itens/servicos', perfil=perfil, body=body, key=uuid4(), query=f"?filial_id={s['outra_filial']}")[0] in (403, 404)


@pytest.mark.parametrize('perfil', ['barbeiro', 'barbeiro_chefe'])
def test_terceiros_negados(pg, runtime_pg, aberta, perfil):
    from app.services.financeiro_errors import ComandaFinanceiraNaoEncontrada
    s = aberta
    if perfil == 'barbeiro': s['atores'][perfil] = s['other']
    with Session(runtime_pg) as db, pytest.raises(ComandaFinanceiraNaoEncontrada):
        incluir(db, s, perfil=perfil)


@pytest.mark.parametrize('modo', ['legado', 'cancelada', 'inativa', 'fechada'])
def test_bloqueios_sem_insercao(pg, runtime_pg, aberta, modo):
    from app.services.financeiro_errors import ErroFinanceiro
    with pg.begin() as conn:
        if modo == 'legado': aberta.update(criar_comanda(conn, aberta, dia='2099-01-02'))
        if modo == 'cancelada': conn.execute(text("UPDATE comandas SET status='cancelada'"))
        if modo == 'inativa': conn.execute(text('UPDATE servicos SET ativo=false'))
    if modo == 'fechada':
        with Session(runtime_pg) as db: fechar(db, aberta, pagamentos=parcelas())
    with Session(runtime_pg) as db, pytest.raises(ErroFinanceiro):
        incluir(db, aberta)
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM inclusoes_servicos_comanda')) == 0


@pytest.mark.parametrize('confirmar', [False, True])
def test_timeout_replay_uma_inclusao(pg, aberta, confirmar):
    from app.services.persistencia import ConfirmacaoIndeterminada
    key = uuid4()
    class Incerta(Session):
        def commit(self):
            if confirmar: super().commit()
            raise OperationalError(None, {}, SimpleNamespace(pgcode='08006'), connection_invalidated=True)
    with Incerta(pg) as db, pytest.raises(ConfirmacaoIndeterminada):
        incluir(db, aberta, chave_idempotencia=key)
    with Session(pg) as db:
        r = incluir(db, aberta, chave_idempotencia=key)
        assert incluir(db, aberta, chave_idempotencia=key) == r
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM inclusoes_servicos_comanda')) == 1
        assert conn.scalar(text('SELECT count(*) FROM itens_comanda')) == 2


def test_auditoria_falha_reverte_item(pg, runtime_pg, aberta):
    def falhar(conn, cursor, sql, params, context, executemany):
        if sql.startswith('INSERT INTO inclusoes_servicos_comanda'): raise RuntimeError('Falha fixture')
    event.listen(runtime_pg, 'before_cursor_execute', falhar)
    try:
        with Session(runtime_pg) as db, pytest.raises(RuntimeError): incluir(db, aberta)
    finally: event.remove(runtime_pg, 'before_cursor_execute', falhar)
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM itens_comanda')) == 1


@pytest.mark.parametrize('primeiro', ['item', 'fechamento', 'replay'])
def test_concorrencia_serializada(pg, aberta, primeiro):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel, SaldoInsuficiente
    key = uuid4()
    add = lambda db: incluir(db, aberta, chave_idempotencia=key)
    close = lambda db: fechar(db, aberta, pagamentos=parcelas())
    um, dois = disputar(pg, add if primeiro != 'fechamento' else close, add if primeiro in ('fechamento', 'replay') else close)
    if primeiro == 'item': assert isinstance(dois, SaldoInsuficiente)
    elif primeiro == 'fechamento': assert isinstance(dois, EstadoFinanceiroIncompativel)
    else: assert um == dois


def test_auditoria_runtime_imutavel(pg, runtime_pg, aberta):
    with Session(runtime_pg) as db: incluir(db, aberta)
    with pytest.raises(DBAPIError):
        with runtime_pg.begin() as conn: conn.execute(text('DELETE FROM inclusoes_servicos_comanda'))


def test_replay_depois_de_fechada_nao_edita(pg, runtime_pg, aberta):
    from datetime import datetime, timezone
    key = uuid4()
    with Session(runtime_pg) as db:
        r = incluir(db, aberta, chave_idempotencia=key)
        fechar(db, aberta, pagamentos=[dict(valor=Decimal('90.50'), forma='pix', confirmado=True, recebido_em=datetime.now(timezone.utc))])
        assert incluir(db, aberta, chave_idempotencia=key) == r
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM itens_comanda')) == 2


@pytest.mark.parametrize('quantidade', [0, 1000, '1', True, 1.5])
def test_http_quantidade_invalida_sem_efeito(api, pg, aberta, quantidade):
    r = requisitar(api, aberta, 'itens/servicos', body=dict(servico_id=str(aberta['service']), quantidade=quantidade), key=uuid4())
    assert r[0] == 422
    with pg.connect() as conn:
        assert conn.scalar(text('SELECT count(*) FROM inclusoes_servicos_comanda')) == 0
