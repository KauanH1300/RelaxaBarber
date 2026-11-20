from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from test_complementos_agenda import requisitar
from test_concorrencia import insert
from test_financeiro_http import api
from test_financeiro_persistencia import data, estornar, financeiro, legado, pagar
from test_financeiro_servicos import caso
from test_produtos_agendados import operar, produto


def montar_insumo(pg, s):
    from app.models.estoque import MovimentoEstoque, ProdutoEstoque
    from app.models.insumos_servico import ConsumoAtendimento

    with Session(pg) as db, db.begin():
        creme = ProdutoEstoque(filial_id=s['filial'], nome='Creme de bancada', unidade='ml', venda=False,
            consumo=True, custo=Decimal('4'), estoque_minimo=0, saldo=8, ativo=True)
        db.add(creme); db.flush()
        baixa = MovimentoEstoque(produto_id=creme.id, filial_id=s['filial'], tipo='baixa', quantidade=-2,
            saldo_apos=8, motivo='Consumo de teste', registrado_por=s['user'], chave_idempotencia=uuid4())
        db.add(baixa); db.flush()
        db.add(ConsumoAtendimento(agendamento_id=s['agendamento'], filial_id=s['filial'], produto_id=creme.id,
            nome=creme.nome, unidade='ml', prevista=3, baixada=2, movimento_id=baixa.id, registrado_por=s['user']))


def test_valores_insumos_produtos_status_e_paginacao(api, pg, runtime_pg, caso, produto):
    from app.services.clientes import garantir_vinculo

    s = caso
    with Session(pg) as db, db.begin():
        garantir_vinculo(db, s['client'], s['filial'])
    operar(runtime_pg, s, produto, uuid4(), acao='adicionar', produto_id=produto, quantidade=2)
    montar_insumo(pg, s)
    with pg.begin() as conn:
        p = pagar(conn, s, valor=Decimal('10'))
        pagar(conn, s, valor=Decimal('5'))
        estornar(conn, s, pagamento=p['id'], valor=Decimal('2'))
        estornar(conn, s, pagamento=p['id'], valor=Decimal('1'))
        outro = insert(conn, s, day='2099-02-01', status='concluido', professional=s['other'])
        cancelado = insert(conn, s, day='2099-03-01', status='cancelado')
        falta = insert(conn, s, day='2099-04-01')
        conn.execute(text("""UPDATE agendamentos SET status='nao_compareceu',falta_registrada_em=now(),
            falta_registrada_por=:ator,falta_motivo='Falta de teste' WHERE id=:id"""), {'ator':s['user'],'id':falta})
        conn.execute(text("UPDATE agendamentos SET observacoes='Preferiu tesoura' WHERE id=:id"),{'id':s['agendamento']})
    rota = f"/clientes/{s['client']}/atendimentos"
    def consultar(perfil='admin', filial=s['filial'], **filtros):
        return requisitar(api, rota, s['atores'][perfil], filial_id=filial, **filtros)
    code, primeira = consultar(tamanho=1)
    assert code == 200, primeira
    assert primeira['proxima_pagina'] == 2
    nao_pago, = primeira['atendimentos']
    assert nao_pago['id'] == str(outro) and 'total_pago_liquido' not in nao_pago
    code, segunda = consultar(tamanho=1, pagina=2)
    assert code == 200 and segunda['proxima_pagina'] is None
    item, = segunda['atendimentos']
    assert item['id'] == str(s['agendamento']) and Decimal(item['total_pago_liquido']) == Decimal('12')
    assert item['servicos'] == [{'nome':'Item ficticio','quantidade':1}]
    assert item['produtos'] == [{'nome':'Produto QA','quantidade':2}]
    assert item['insumos'] == [{'nome':'Creme de bancada','unidade':'ml','quantidade':'2.000'}]
    assert item['observacoes'] == 'Preferiu tesoura'
    assert [x['id'] for x in consultar(incluir_ocorrencias='true')[1]['atendimentos'][:2]] == [str(falta),str(cancelado)]
    for papel in ('recepcao','barbeiro','barbeiro_chefe'):
        code, resposta = consultar(papel)
        assert code == 200 and resposta['atendimentos']
        assert all('total_pago_liquido' not in x for x in resposta['atendimentos'])
        assert 'preco' not in str(resposta) and 'custo' not in str(resposta)
    assert [x['id'] for x in consultar('barbeiro')[1]['atendimentos']] == [str(s['agendamento'])]
    assert consultar(filial=s['outra_filial'])[0] == 404
    assert consultar('recepcao', filial=s['outra_filial'])[0] == 403
    with Session(pg) as db, db.begin():
        garantir_vinculo(db, s['client'], s['outra_filial'])
    assert consultar(filial=s['outra_filial'])[1]['atendimentos'] == []


def test_migracao_grant_colunar(pg):
    # Sem runtime_pg, para verificar os grants da migração antes do provisionamento legado.
    with pg.connect() as conn:
        for papel in ('relaxabarber_runtime', 'relaxabarber_dev_app'):
            assert conn.scalar(text("SELECT has_column_privilege(:p,'public.agendamentos','observacoes','UPDATE')"),
                               {'p': papel})
        # O PostgreSQL descartável provisiona grants amplos nas tabelas legadas.
        # Verifique a ACL colunar da revisão sem confundi-la com esse acesso de tabela.
        assert conn.execute(text("""
            SELECT grantee::regrole::text, privilege_type, is_grantable
            FROM pg_attribute, LATERAL aclexplode(attacl)
            WHERE attrelid = 'public.agendamentos'::regclass AND attname = 'observacoes'
        """)).all() == [('relaxabarber_runtime', 'UPDATE', False)]


def test_observacoes_permissoes_e_versao(api, caso):
    s = caso
    base = f"/agendamentos/{s['agendamento']}"
    codigo, atual = requisitar(api, base, s['atores']['admin'], filial_id=s['filial'])
    assert codigo == 200, atual
    def alterar(ator, campos=None, filial=s['filial']):
        return requisitar(api, base+'/observacoes', ator, method='PATCH', filial_id=filial, dados={
            'observacoes':'  Atendimento revisado  ', 'atualizado_em_esperado':atual['atualizado_em'],
        } | (campos or {}))
    assert alterar(s['atores']['outro'])[0] == 404
    assert alterar(s['atores']['recepcao'], filial=s['outra_filial'])[0] == 403
    assert alterar(s['atores']['admin'], {'observacoes':'a'*1001})[0] == 422
    codigo, editado = alterar(s['atores']['barbeiro'])
    assert codigo == 200 and editado['observacoes'] == 'Atendimento revisado'
    assert alterar(s['atores']['recepcao'])[0] == 409
    codigo, limpo = alterar(s['atores']['recepcao'],
        {'observacoes':None,'atualizado_em_esperado':editado['atualizado_em']})
    assert codigo == 200 and limpo['observacoes'] is None
