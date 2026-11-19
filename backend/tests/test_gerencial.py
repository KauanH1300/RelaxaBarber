from datetime import date, datetime, time
from decimal import Decimal
from types import SimpleNamespace as Registro
from uuid import uuid4
from zoneinfo import ZoneInfo


def test_agrega_descontos_cortesia_avulsa_sem_confundir_caixa_e_faturamento():
    from app.services.gerencial import apurar

    fuso = ZoneInfo('America/Recife')
    dia = date(2026, 11, 19)
    ontem = date(2026, 11, 18)
    barbeiro, cliente = uuid4(), uuid4()
    servico = Registro(id=uuid4(), ativo=True, tipo='servico', servico_id=uuid4(),
                       descricao='Corte', quantidade=2, preco_unitario=Decimal('30.00'),
                       desconto_tipo='valor', desconto_valor=Decimal('10.00'))
    cortesia = Registro(id=uuid4(), ativo=True, tipo='servico', servico_id=uuid4(),
                        descricao='Cortesia', quantidade=1, preco_unitario=Decimal('25.00'),
                        desconto_tipo='cortesia', desconto_valor=Decimal('0.00'))
    produto = Registro(id=uuid4(), ativo=True, tipo='produto', quantidade=1, preco_unitario=Decimal('50.00'))
    atendimento = Registro(tipo='agendada', barbeiro_id=barbeiro, itens=[servico, cortesia, produto],
                           desconto_tipo='percentual', desconto_valor=Decimal('10.00'))
    avulsa = Registro(tipo='avulsa', barbeiro_id=None, itens=[produto],
                      desconto_tipo='nenhum', desconto_valor=Decimal('0.00'))
    instante = datetime.combine(dia, time(9), fuso)
    fechamentos = [(Registro(total=Decimal('90.00'), registrado_em=instante), atendimento),
                   (Registro(total=Decimal('50.00'), registrado_em=instante), avulsa)]
    caixa = [(barbeiro, ontem, Decimal('30.00'), Decimal('0.00')),
             (barbeiro, dia, Decimal('0.00'), Decimal('5.50'))]
    agenda = [Registro(status=s, data=dia, hora_inicio=time(9), barbeiro_id=barbeiro, cliente_id=cliente)
              for s in ('concluido', 'concluido', 'cancelado', 'nao_compareceu')]
    dados = apurar(fechamentos, caixa, agenda, fuso, 'dia')
    i = dados['indicadores']
    assert (i['bruto'], i['faturado'], i['recebido_liquido']) == (Decimal('185'), Decimal('140'), Decimal('24.50'))
    assert (i['concluidos'], i['clientes'], i['base_ticket'], i['ticket_medio']) == (2, 1, 1, Decimal('90'))
    assert i['taxa_cancelamento'] == i['taxa_falta'] == Decimal('25')
    assert dados['dias'] == {dia.weekday(): 2}
    assert dados['horarios'] == {9: 2}
    assert dados['periodos'][0]['periodo'] == ontem
    assert dados['periodos'][0]['faturado'] == 0
    assert {s['nome']: (s['quantidade'], s['faturado']) for s in dados['servicos']} == {
        'Corte': (2, Decimal('45')), 'Cortesia': (1, Decimal('0')),
    }

