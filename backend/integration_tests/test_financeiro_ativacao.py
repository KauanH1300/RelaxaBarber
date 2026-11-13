"""Ativação pelo fluxo real, somente no PostgreSQL descartável do conftest."""
from datetime import date, time, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from test_concorrencia import data
from test_financeiro_persistencia import legado


def criar(db, s):
    from app.models import Usuario
    from app.schemas.agendamento import AgendamentoCreate
    from app.services.agendamento import criar_agendamento
    return criar_agendamento(AgendamentoCreate(
        filial_id=s['filial'], cliente_id=s['client'], barbeiro_id=s['user'],
        data=date(2099, 1, 2), hora_inicio=time(9),
        servicos=[{'servico_id': s['service']}],
    ), db, db.get(Usuario, s['user']))


@pytest.mark.parametrize('zero', [False, True])
def test_criacao_atomica_aberta_inclusive_zero(runtime_pg, data, zero):
    from app.models import Comanda, ControleFinanceiroComanda
    from app.services.financeiro import consultar_situacao
    from app.models import Usuario
    if zero:
        with runtime_pg.begin() as conn:
            conn.execute(text('UPDATE servicos SET preco=0 WHERE id=:service'), data)
    commits = []
    with Session(runtime_pg, autoflush=False) as db:
        event.listen(db, 'after_commit', lambda session: commits.append(True))
        a = criar(db, data)
        c = db.scalar(select(Comanda).where(Comanda.agendamento_id == a.id))
        controle = db.get(ControleFinanceiroComanda, c.id)
        assert controle.filial_id == c.filial_id == data['filial']
        assert controle.registrado_por == data['user'] and controle.motivo.strip()
        assert controle.registrado_em is not None
        assert c.status == a.status == 'pendente'
        assert len(c.itens) == len(a.servicos) == 1
        resumo = consultar_situacao(c.id, db, db.get(Usuario, data['user']))
        assert c.situacao_financeira == resumo.situacao == 'aberto'
        assert resumo.saldo == resumo.total == (Decimal('0') if zero else Decimal('30'))
        assert resumo.pagamentos == resumo.estornos == resumo.recebido_liquido == 0
    assert len(commits) == 1


@pytest.mark.parametrize('falha', ['controle', 'itens', 'antes_commit'])
def test_falha_reverte_todo_o_agregado(runtime_pg, data, falha):
    from app.services.persistencia import FalhaPersistencia
    inseridos = []
    def interceptar(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO'):
            inseridos.append(statement)
        alvo = {'controle': 'controles_financeiros_comanda', 'itens': 'itens_comanda'}.get(falha)
        if alvo and statement.startswith('INSERT INTO ' + alvo):
            raise RuntimeError('Falha injetada antes do INSERT')
    def antes_commit(session):
        session.flush()  # prova rollback com todos os INSERTs já executados
        raise RuntimeError('Falha injetada após flush')
    event.listen(runtime_pg, 'before_cursor_execute', interceptar)
    try:
        with Session(runtime_pg, autoflush=False) as db:
            if falha == 'antes_commit':
                event.listen(db, 'before_commit', antes_commit)
            with pytest.raises((RuntimeError, FalhaPersistencia)):
                criar(db, data)
            assert db.scalar(text('SELECT 1')) == 1
    finally:
        event.remove(runtime_pg, 'before_cursor_execute', interceptar)
    assert any('INSERT INTO agendamentos' in sql for sql in inseridos)
    with runtime_pg.connect() as conn:
        for tabela in ('agendamentos', 'agendamento_servicos', 'comandas', 'itens_comanda',
                       'controles_financeiros_comanda', 'cliente_filiais'):
            assert conn.scalar(text(f'SELECT count(*) FROM {tabela}')) == 0


@pytest.mark.parametrize('cancelar', [True, False])
def test_transicoes_operacionais_nao_movimentam_financeiro(runtime_pg, data, cancelar):
    from app.models import Comanda, Usuario
    from app.schemas.agendamento import AgendamentoStatusUpdate
    from app.services.agendamento import atualizar_status
    from app.services.financeiro import registrar_pagamento, consultar_situacao
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with Session(runtime_pg) as db:
        a = criar(db, data)
        u = db.get(Usuario, data['user'])
        c = db.scalar(select(Comanda).where(Comanda.agendamento_id == a.id))
        for estado in (['aguardando', 'cancelado'] if cancelar else ['aguardando', 'em_atendimento', 'concluido']):
            atualizar_status(a.id, AgendamentoStatusUpdate(status=estado,
                motivo_cancelamento='Solicitação' if estado == 'cancelado' else None), db, u)
        db.refresh(c)
        assert c.status == ('cancelada' if cancelar else 'fechada')
        assert (c.data_fechamento is not None) == (not cancelar)
        assert consultar_situacao(c.id, db, u).situacao == 'aberto'
        for tabela in ('pagamentos_comanda', 'estornos_pagamento', 'fechamentos_financeiros_comanda'):
            assert db.scalar(text(f'SELECT count(*) FROM {tabela}')) == 0
        args = dict(valor=Decimal('1'), forma='pix', recebido_em=datetime.now(timezone.utc),
                    chave_idempotencia=uuid4(), db=db, usuario=u)
        if cancelar:
            with pytest.raises(EstadoFinanceiroIncompativel):
                registrar_pagamento(c.id, **args)
        else:
            registrar_pagamento(c.id, **args)
            assert consultar_situacao(c.id, db, u).saldo == Decimal('29')


def test_nova_comanda_nao_concilia_legado(pg, legado):
    from app.models import Comanda, Usuario
    from app.services.financeiro import consultar_situacao
    with Session(pg) as db:
        criar(db, legado)
        c = db.get(Comanda, legado['comanda'])
        resumo = consultar_situacao(c.id, db, db.get(Usuario, legado['user']))
        assert c.situacao_financeira == resumo.situacao == 'nao_verificado'
        assert resumo.saldo is resumo.recebido_liquido is None
        assert db.scalar(text('SELECT count(*) FROM controles_financeiros_comanda')) == 1
