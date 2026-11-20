from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy.orm import Session
from sqlalchemy import text

from test_financeiro_persistencia import data, financeiro, legado
from test_financeiro_servicos import caso
from test_financeiro_http import api, pagar, preparar_pagamento
from test_financeiro_historico import estornar
from test_seguranca_horarios import chamar


def requisitar(api, s, rota, *, perfil='admin', filial=None, method='GET', dados=None):
    from app.core.security import criar_token

    params = '?' + urlencode({'filial_id': filial}) if filial else ''
    return chamar(api, rota + params, method=method, dados=dados, token=criar_token(s['atores'][perfil]))


def test_perfil_opcional_validado_e_isolado(api, caso):
    s = caso
    dados = dict(nome='Perfil de teste', telefone='81900001111', filial_id=str(s['filial']))
    for alteracoes in ({'data_nascimento': '2099-01-01'}, {'data_nascimento': '2024-02-30'},
                        {'data_nascimento': 112233}, {'preferencias': 'x' * 2001}):
        assert requisitar(api,s,'/clientes',perfil='recepcao',method='POST',dados=dados | alteracoes)[0] == 422
    codigo, cliente = requisitar(api,s,'/clientes',perfil='recepcao',method='POST',
        dados=dados | {'data_nascimento': '2000-02-29', 'preferencias': '  Prefere tesoura  '})
    assert codigo == 201, cliente
    assert (cliente['data_nascimento'], cliente['preferencias']) == ('2000-02-29','Prefere tesoura')
    rota = '/clientes/' + cliente['id']
    assert requisitar(api,s,rota,filial=s['outra_filial'])[0] == 404
    assert requisitar(api,s,rota,filial=s['outra_filial'],method='PATCH',dados={'preferencias': None})[0] == 404
    assert requisitar(api,s,rota,perfil='recepcao',filial=s['outra_filial'])[0] == 403
    pesquisa = requisitar(api,s,'/clientes/pesquisa',perfil='recepcao',filial=s['filial'])[1]
    assert all('preferencias' not in c and 'data_nascimento' not in c for c in pesquisa)
    atual = requisitar(api,s,rota,perfil='recepcao',filial=s['filial'],method='PATCH',dados={'preferencias':'   '})[1]
    assert atual['preferencias'] is None and atual['data_nascimento'] == '2000-02-29'
    atual = requisitar(api,s,rota,perfil='recepcao',filial=s['filial'],method='PATCH',dados={'data_nascimento':None})[1]
    assert atual['data_nascimento'] is None


def test_historico_liquido_e_vinculos(api, pg, caso):
    from app.services.clientes import garantir_vinculo

    s = caso
    with Session(pg) as db, db.begin():
        garantir_vinculo(db,s['client'],s['filial'])
    rota = f"/clientes/{s['client']}/resumo-financeiro"
    assert requisitar(api,s,rota,filial=s['outra_filial'])[0] == 404
    for papel in ('recepcao','barbeiro','barbeiro_chefe'):
        assert requisitar(api,s,rota,perfil=papel,filial=s['filial'])[0] == 403
        codigo, resumo = requisitar(api,s,rota.replace('-financeiro',''),perfil=papel,filial=s['filial'])
        assert codigo == 200 and 'movimentacoes' not in resumo and 'total_gasto' not in resumo

    codigo, vazio = requisitar(api,s,rota,filial=s['filial'])
    assert codigo == 200, vazio
    assert Decimal(vazio['total_gasto']) == 0 and vazio['movimentacoes'] == []
    assert vazio['escopo_filiais'] == 'filial'

    _, parcial = preparar_pagamento(pg,s,valor='10.00')
    assert estornar(api,s,parcial['id'],'2.00')[0] == 200
    assert estornar(api,s,parcial['id'],'1.00')[0] == 200
    assert pagar(api,s,valor='23.50')[0] == 200
    with Session(pg) as db, db.begin():
        garantir_vinculo(db,s['client'],s['outra_filial'])
    codigo, financeiro_cliente = requisitar(api,s,rota)
    assert codigo == 200, financeiro_cliente
    assert Decimal(financeiro_cliente['total_gasto']) == Decimal('30.50')
    linha, = financeiro_cliente['movimentacoes']
    assert [Decimal(linha[k]) for k in ('recebido','estornado','total_gasto')] == [
        Decimal('33.50'),Decimal('3.00'),Decimal('30.50'),
    ]
    assert Decimal(requisitar(api,s,rota,filial=s['outra_filial'])[1]['total_gasto']) == 0
    assert Decimal(requisitar(api,s,rota,filial=s['filial'])[1]['total_gasto']) == Decimal('30.50')


def test_comissoes_da_comanda_restritas_sem_bloquear_operacao(api, caso):
    s = caso
    rota = f"/comissoes/comandas/{s['comanda']}"
    operacional = f"/comandas/{s['comanda']}/financeiro"
    for sufixo in ('','/historico'):
        assert chamar(api, rota + sufixo)[0] == 401
        assert requisitar(api,s,rota + sufixo,filial=s['filial'])[0] == 200
        for papel in ('recepcao','barbeiro','barbeiro_chefe'):
            assert requisitar(api,s,rota + sufixo,perfil=papel,filial=s['filial'])[0] == 403
    for papel in ('recepcao','barbeiro'):
        assert requisitar(api,s,operacional,perfil=papel,filial=s['filial'])[0] == 200


def test_migracao_concede_update_colunar(pg):
    with pg.connect() as db:
        for coluna in ('data_nascimento','preferencias'):
            assert db.scalar(text("SELECT has_column_privilege('relaxabarber_dev_app','public.clientes',:c,'UPDATE')"),{'c':coluna})
