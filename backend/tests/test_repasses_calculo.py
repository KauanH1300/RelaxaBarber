from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from app.services.repasses_calculo import ComissaoAtual, EventoAcumulado, ParcelaCongelada, demonstrar, estados_atuais

D = Decimal
INICIO, FIM = date(2026, 1, 1), date(2026, 1, 31)


def atual(item, liberada, gerada='20', origem=date(2026, 1, 15)):
    return ComissaoAtual(item, uuid4(), origem, D(gerada), D(liberada))


def parcela(item, valor, pago='0', ordem=1):
    return ParcelaCongelada(uuid4(), item, ordem, D(valor), D(pago))


def test_pagamento_tardio_origina_complemento_sem_duplicar_fechamento():
    item = uuid4()
    fechado = parcela(item, '5')
    primeiro = demonstrar([atual(item, '5')], [fechado], INICIO, FIM)
    assert primeiro.elegivel_periodo == 0 and primeiro.parcelas[0].disponivel == 5
    tardio = demonstrar([atual(item, '12')], [fechado], INICIO, FIM)
    assert tardio.elegivel_periodo == 7 and tardio.credito_por_item[item] == 7
    complementar = parcela(item, '7', ordem=2)
    assert demonstrar([atual(item, '12')], [fechado, complementar], INICIO, FIM).elegivel_periodo == 0


def test_queda_recuperacao_e_fechamentos_sobrepostos_nao_duplicam():
    item = uuid4()
    parcelas = [parcela(item, '5', ordem=1), parcela(item, '5', ordem=2)]
    queda = demonstrar([atual(item, '6')], parcelas, INICIO, FIM)
    assert [p.disponivel for p in queda.parcelas] == [5, 1]
    assert sum(p.ajuste_negativo for p in queda.parcelas) == 4
    recuperado = demonstrar([atual(item, '10')], parcelas, date(2026, 1, 10), date(2026, 2, 10))
    assert recuperado.elegivel_periodo == 0
    assert sum(p.disponivel for p in recuperado.parcelas) == 10


def test_deficit_pago_bloqueia_novos_repasses_e_creditos():
    item, outro = uuid4(), uuid4()
    fechamento = parcela(item, '10', pago='8')
    saldo = demonstrar([atual(item, '6'), atual(outro, '5')], [fechamento], INICIO, FIM)
    assert saldo.deficit_pago == 2 and saldo.bloqueio_por_deficit
    assert saldo.elegivel_periodo == 0 and saldo.parcelas[0].disponivel == 0


def test_estorno_de_repasse_reduz_liquido_sem_mudar_valor_congelado():
    item = uuid4()
    fechamento = parcela(item, '10', pago='4')
    saldo = demonstrar([atual(item, '10')], [fechamento], INICIO, FIM)
    assert saldo.parcelas[0].congelado == 10 and saldo.parcelas[0].disponivel == 6


def test_rejeita_parcela_orfa_duplicada_valores_invalidos_e_periodo_invertido():
    item = uuid4()
    fechamento = parcela(item, '10')
    with pytest.raises(ValueError): demonstrar([], [fechamento], INICIO, FIM)
    with pytest.raises(ValueError): demonstrar([atual(item, '10')], [fechamento, fechamento], INICIO, FIM)
    with pytest.raises(ValueError): demonstrar([atual(item, '21')], [], INICIO, FIM)
    with pytest.raises(ValueError): demonstrar([atual(item, '10')], [], FIM, INICIO)


def test_transferencia_nao_ressuscita_saldo_do_profissional_anterior():
    item, filial, antigo, novo = uuid4(), uuid4(), uuid4(), uuid4()
    eventos = [EventoAcumulado(item, uuid4(), antigo, filial, 1, INICIO, D('10'), D('3')),
               EventoAcumulado(item, uuid4(), novo, filial, 2, INICIO, D('10'), D('0'))]
    assert estados_atuais(eventos, antigo, filial) == []
    assert len(estados_atuais(list(reversed(eventos)), novo, filial)) == 1
    with pytest.raises(ValueError): estados_atuais(eventos, novo, uuid4())
    with pytest.raises(ValueError): estados_atuais([eventos[0], eventos[0]], antigo, filial)
