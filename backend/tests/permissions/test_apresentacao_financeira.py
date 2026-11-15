"""Classificação real SQL/ORM, sem rede nem reclassificação de registros."""
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from test_filiais import unidades


def caso(s, models, *, legado=False, pago='0.00', fechado=False, inconsistente=False):
    a = s.bookings[('barbeiro', 'A')]
    a.status = 'concluido'
    c = s.db.scalar(select(models.Comanda).where(models.Comanda.agendamento_id == a.id))
    c.status = 'fechada' if legado else 'aberta'
    if legado:
        s.db.query(models.ControleFinanceiroComanda).filter_by(comanda_id=c.id).delete()
    if Decimal(pago):
        s.db.add(models.PagamentoComanda(comanda_id=c.id, filial_id=c.filial_id,
            registrado_por=s.users['admin'].id, valor=Decimal(pago), forma='pix',
            recebido_em=datetime(2099, 2, 2, tzinfo=timezone.utc), chave_idempotencia=uuid4(), fingerprint='a'*64))
    if fechado:
        c.status = 'fechada'
        s.db.add(models.FechamentoFinanceiroComanda(comanda_id=c.id, filial_id=c.filial_id,
            registrado_por=s.users['admin'].id, total=Decimal('29.00' if inconsistente else '30.00'),
            recebido_liquido=Decimal('29.00' if inconsistente else '30.00'),
            registrado_em=datetime(2099, 2, 2, 2, 30, tzinfo=timezone.utc),
            chave_idempotencia=uuid4(), fingerprint='b'*64))
    s.db.commit()
    return c


@pytest.mark.parametrize('options,estado,saldo', [
    ({}, 'pagamento_pendente', '30.00'),
    ({'legado': True}, 'nao_verificado', None),
    ({'pago': '30.00'}, 'aguardando_fechamento', '0.00'),
    ({'pago': '30.00', 'fechado': True}, 'fechada', '0.00'),
    ({'pago': '30.00', 'fechado': True, 'inconsistente': True}, 'nao_verificado', None),
])
def test_classificacao_nao_muda_historico(unidades, models, options, estado, saldo):
    from app.services.comandas import buscar_detalhe
    s = unidades
    c = caso(s, models, **options)
    original = (c.status, c.data_fechamento)
    result = buscar_detalhe(s.db, s.users['admin'], c.id, s.a.id)
    assert result.status_apresentacao == estado
    assert (str(result.saldo_financeiro) if result.saldo_financeiro is not None else None) == saldo
    assert (c.status, c.data_fechamento) == original
    assert not s.db.dirty and not s.db.new


def test_fechadas_por_data_financeira_recife_nao_atendimento(unidades, models):
    from app.services.comandas import consultar_painel
    s = unidades
    c = caso(s, models, pago='30.00', fechado=True)
    # Atendimento em janeiro; fechamento 02/02 02:30 UTC = 01/02 23:30 Recife.
    result = consultar_painel(s.db, s.users['admin'], s.a.id, status_financeiro='fechada',
        data_inicio=date(2099, 2, 1), data_fim=date(2099, 2, 1))
    assert result.total == 1 and result.itens[0].id == c.id
    assert result.indicadores.fechadas_periodo == 1
    assert consultar_painel(s.db, s.users['admin'], s.a.id, status_financeiro='fechada',
        data_inicio=date(2099, 2, 2), data_fim=date(2099, 2, 2)).total == 0


def test_saldos_sem_multiplicar_joins_e_sem_legado(unidades, models):
    from app.services.comandas import consultar_painel
    s = unidades
    c = caso(s, models, pago='10.00')
    s.db.add(models.ItemComanda(comanda_id=c.id, tipo='servico', descricao='Adicional',
                               quantidade=2, preco_unitario=Decimal('5.00')))
    s.db.add(models.EstornoPagamento(comanda_id=c.id, filial_id=c.filial_id,
        pagamento_id=s.db.scalar(select(models.PagamentoComanda.id)), valor=Decimal('2.00'),
        motivo='Fixture', efetivado_em=datetime(2099, 2, 2, tzinfo=timezone.utc),
        registrado_por=s.users['admin'].id, chave_idempotencia=uuid4(), fingerprint='c'*64))
    s.db.commit()
    result = consultar_painel(s.db, s.users['admin'], s.a.id, profissional_id=c.barbeiro_id)
    assert result.total == 1 and result.indicadores.aguardando_pagamento == 1
    assert result.indicadores.valor_abertas == Decimal('32.00')


def test_chefe_nao_recebe_financeiro_de_outro_e_filial_isolada(unidades, models):
    from app.services.comandas import buscar_detalhe, consultar_painel
    from app.services.errors import RecursoNaoEncontrado
    s = unidades
    c = caso(s, models, pago='30.00', fechado=True)
    detalhe = buscar_detalhe(s.db, s.users['barbeiro_chefe'], c.id, s.a.id)
    assert detalhe.status_apresentacao == 'restrito'
    assert detalhe.saldo_financeiro is None and detalhe.fechamento_financeiro_em is None
    painel = consultar_painel(s.db, s.users['barbeiro_chefe'], s.a.id, profissional_id=c.barbeiro_id)
    assert painel.indicadores.fechadas_periodo == 0 and painel.indicadores.valor_abertas == 0
    with pytest.raises(RecursoNaoEncontrado):
        buscar_detalhe(s.db, s.users['admin'], c.id, s.b.id)


@pytest.mark.parametrize('role', ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe'])
def test_financeiro_proprio_autorizado_para_quatro_perfis(unidades, models, role):
    from app.services.comandas import buscar_detalhe
    s = unidades
    c = caso(s, models)
    if role == 'barbeiro_chefe':
        c = s.db.scalar(select(models.Comanda).where(
            models.Comanda.agendamento_id == s.bookings[('barbeiro_chefe', 'A')].id))
        s.bookings[('barbeiro_chefe', 'A')].status = 'concluido'
        s.db.commit()
    result = buscar_detalhe(s.db, s.users[role], c.id, s.a.id)
    assert result.status_apresentacao == 'pagamento_pendente'
    assert result.saldo_financeiro == Decimal('30.00')


@pytest.mark.parametrize('alteracao,estado', [
    ('cancelada', 'cancelada'), ('agendada', 'aberta'),
    ('recebimento_excessivo', 'nao_verificado'),
])
def test_cancelamento_e_inconsistencia_nao_sao_quitacao(unidades, models, alteracao, estado):
    from app.services.comandas import buscar_detalhe
    s = unidades
    c = caso(s, models, pago='31.00' if alteracao == 'recebimento_excessivo' else '0.00')
    if alteracao == 'cancelada':
        c.status = 'cancelada'
    elif alteracao == 'agendada':
        s.bookings[('barbeiro', 'A')].status = 'pendente'
    s.db.commit()
    result = buscar_detalhe(s.db, s.users['admin'], c.id, s.a.id)
    assert result.status_apresentacao == estado
    if estado != 'aberta':
        assert result.saldo_financeiro is None
    assert result.fechamento_financeiro_em is None
