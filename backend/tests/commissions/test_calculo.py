from decimal import Decimal as D
from types import SimpleNamespace
from uuid import UUID
from app.services.comissoes_calculo import calcular, ratear


def item(n, preco, tipo='servico', desconto_tipo='nenhum', desconto_valor='0'):
    return SimpleNamespace(id=UUID(int=n), quantidade=1, preco_unitario=D(preco), tipo=tipo,
                           desconto_tipo=desconto_tipo, desconto_valor=D(desconto_valor), ativo=True)


def test_rateio_de_desconto_geral_e_pagamento_parcial():
    a, b = item(1, '10.00'), item(2, '20.00')
    p = {a.id: D('10'), b.id: D('20')}
    valores = calcular([a,b], 'valor', D('3.00'), p, D('13.50'))
    assert [(v.base,v.gerada,v.liberada) for v in valores] == [(D('9.00'),D('0.90'),D('0.45')),(D('18.00'),D('3.60'),D('1.80'))]
    assert calcular([a,b], 'valor', D('3.00'), p, D('27.00'))[1].liberada == D('3.60')
    assert calcular([a,b], 'valor', D('3.00'), p, D('0.00'))[1].liberada == D('0.00')


def test_cortesia_e_produto_sem_vendedor_nao_geram_comissao():
    a, b = item(1,'10.00',desconto_tipo='cortesia'), item(2,'10.00',tipo='produto')
    valores = calcular([a,b], 'nenhum', D('0'), {a.id:D('50'), b.id:D('50')}, D('5.00'))
    assert len(valores)==1 and valores[0].base==valores[0].gerada==valores[0].liberada==0


def test_rateio_de_centavo_e_estavel_independente_da_ordem():
    a,b,c = (UUID(int=i) for i in (1,2,3))
    assert ratear(D('0.01'), {c:D('1'),b:D('1'),a:D('1')}) == {a:D('0.01'),b:D('0'),c:D('0')}


def test_liberacao_parcial_rateia_arredondamento_global_sem_exceder_total():
    a,b=item(1,'0.01'),item(2,'0.01')
    result=calcular([a,b],'nenhum',D('0'),{a.id:D('100'),b.id:D('100')},D('0.01'))
    assert sum((r.gerada for r in result),D('0'))==D('0.02')
    assert sum((r.liberada for r in result),D('0'))==D('0.01')
    assert [r.liberada for r in result]==[D('0.01'),D('0.00')]
