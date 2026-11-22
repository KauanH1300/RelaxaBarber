from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from test_clientes_duplicados import cadastrar
from test_complementos_agenda import api, criar_recepcao, data, duas_filiais, requisitar
from test_financeiro_persistencia import pagar, estornar
from test_reserva_publica import agenda
from test_seguranca_horarios import chamar


ROTA = '/clientes/duplicidades/revisoes'
TELEFONE = '81999991234'


@pytest.fixture
def duplicata(api, pg, agenda, duas_filiais):
    from app.models import Cliente
    from app.services.clientes import garantir_vinculo

    s = duas_filiais | {'token': agenda['token'], 'engine': agenda['engine']}
    with Session(pg) as db, db.begin():
        db.get(Cliente, s['client']).telefone = TELEFONE
        garantir_vinculo(db, s['client'], s['filial'])
    presencial = cadastrar(api, s, 'Ficha presencial', '(81) 99999-1234')
    return s | {'presencial': UUID(presencial), 'recepcao': criar_recepcao(pg, s)}


def decisao(s, acao='associar', versao=None, **campos):
    return dict(cliente_a=str(s['client']), cliente_b=str(s['presencial']), acao=acao,
                versao=versao, chave=str(uuid4()), justificativa='Conferência no atendimento',
                identidade_confirmada=True, metodo='presencial_e_atendimentos') | campos


def enviar(api, s, dados, ator='admin', filial=None):
    return requisitar(api, ROTA, s[ator], method='POST', dados=dados, filial_id=filial or s['filial'])


def reservar(api, s, cliente, *, ator='admin', dia='2099-05-20', hora='09:00', filial=None):
    return requisitar(api, '/agendamentos', s[ator], method='POST', dados={
        'cliente_id': str(cliente), 'barbeiro_id': str(s['user']), 'filial_id': str(filial or s['filial']),
        'data': dia, 'hora_inicio': hora, 'servicos': [{'servico_id': str(s['service'])}],
    })


def ids_api(api, s, caminho, busca='', filial=None):
    status, resposta = requisitar(api, caminho, s['recepcao'], filial_id=filial or s['filial'], busca=busca)
    assert status == 200, resposta
    return {r['id'] for r in resposta}


def abrir_avulsa(api, s, cliente, chave=None, filial=None):
    from app.core.security import criar_token

    async def app(scope, receive, send):
        scope = dict(scope, headers=[*scope['headers'], (b'idempotency-key', str(chave or uuid4()).encode())])
        await api(scope, receive, send)

    return chamar(app, f"/comandas/avulsas?filial_id={filial or s['filial']}", method='POST',
                  dados={'cliente_id': str(cliente)}, token=criar_token(s['admin']))


def test_associacao_usa_principal_em_seletores_agenda_avulsa_e_pode_desfazer(api, pg, duplicata):
    from app.models import Agendamento, Comanda, DecisaoCliente, EventoComissao
    from app.services import minha_agenda, portal_cliente

    s = duplicata
    status, historico = reservar(api, s, s['presencial'])
    assert status == 201, historico
    id_historico = UUID(historico['id'])
    with pg.begin() as db:
        db.execute(text("UPDATE agendamentos SET status='concluido' WHERE id=:id"), {'id': id_historico})
        comanda = db.execute(text("UPDATE comandas SET status='aberta' WHERE agendamento_id=:id RETURNING id"),
                             {'id': id_historico}).scalar_one()
        financeiro = s | {'comanda': comanda}
        pagamento = pagar(db, financeiro, valor=Decimal('10'))
        estornar(db, financeiro, pagamento=pagamento['id'], valor=Decimal('2'))
        comissoes_originais = set(db.execute(select(EventoComissao.id, EventoComissao.gerada)
                                             .where(EventoComissao.comanda_id == comanda)))
        assert comissoes_originais

    assert enviar(api, s, decisao(s), ator='recepcao')[0] == 403
    assert enviar(api, s, decisao(s, identidade_confirmada=False))[0] == 422
    assert enviar(api, s, decisao(s, cliente_b=str(s['client'])))[0] == 422
    status, encaminhada = enviar(api, s, decisao(s, 'encaminhar'), ator='recepcao')
    assert status == 200, encaminhada
    comando = decisao(s, versao=encaminhada['versao'])
    status, resposta = enviar(api, s, comando)
    assert status == 200 and resposta['principal_id'] == str(s['client']), resposta
    assert enviar(api, s, comando) == (status, resposta)
    assert enviar(api, s, comando | {'justificativa': 'Outro conteúdo'})[0] == 409

    for rota in ('/clientes', '/clientes/pesquisa', '/clientes/coincidencias'):
        if rota.endswith('coincidencias'):
            codigo, resultados = requisitar(api, rota, s['recepcao'], filial_id=s['filial'], telefone=TELEFONE)
            assert codigo == 200 and {r['id'] for r in resultados} == {str(s['client'])}
        else:
            assert ids_api(api, s, rota, busca='Ficha presencial') == {str(s['client'])}
    codigo, seletor = requisitar(api, '/clientes/pesquisa', s['user'], filial_id=s['filial'])
    assert codigo == 200 and {r['id'] for r in seletor} == {str(s['client'])}
    assert requisitar(api, '/clientes/pesquisa', s['user'], filial_id=s['second'])[1] == []
    for ator, hora in [('user', '10:00'), ('recepcao', '11:00')]:
        codigo, reserva = reservar(api, s, s['presencial'], ator=ator, hora=hora)
        assert codigo == 201 and reserva['cliente_id'] == str(s['client']), reserva
    chave = uuid4()
    codigo, avulsa = abrir_avulsa(api, s, s['presencial'], chave)
    assert codigo == 201, avulsa
    assert abrir_avulsa(api, s, s['presencial'], chave) == (codigo, avulsa)

    perfil = f"/clientes/{s['client']}"
    codigo, linha = requisitar(api, perfil + '/atendimentos', s['admin'], filial_id=s['filial'])
    assert codigo == 200 and linha['atendimentos'][0]['id'] == str(id_historico)
    assert Decimal(linha['atendimentos'][0]['total_pago_liquido']) == Decimal('8')
    codigo, linha_recepcao = requisitar(api, perfil + '/atendimentos', s['recepcao'], filial_id=s['filial'])
    assert codigo == 200 and 'total_pago_liquido' not in linha_recepcao['atendimentos'][0]
    codigo, resumo = requisitar(api, perfil + '/resumo-financeiro', s['admin'], filial_id=s['filial'])
    assert codigo == 200 and Decimal(resumo['total_gasto']) == Decimal('8'), resumo
    assert requisitar(api, perfil + '/resumo-financeiro', s['recepcao'], filial_id=s['filial'])[0] == 403
    assert requisitar(api, perfil + '/atendimentos', s['admin'], filial_id=s['second'])[0] == 404
    assert reservar(api, s, s['presencial'], filial=s['second'], hora='12:00')[0] == 404
    assert abrir_avulsa(api, s, s['presencial'], filial=s['second'])[0] == 422
    with Session(s['engine']) as db:
        assert id_historico not in {r.id for r in minha_agenda.listar(db, s['token'])}
        assert portal_cliente.autenticar(db, s['token']).id == s['client']
        from app.services.errors import RecursoNaoEncontrado
        with pytest.raises(RecursoNaoEncontrado):
            minha_agenda.consultar(db, s['token'], id_historico)
        assert db.get(Agendamento, id_historico).cliente_id == s['presencial']
        assert db.get(Comanda, comanda).cliente_id == s['presencial']
        assert set(db.execute(select(EventoComissao.id, EventoComissao.gerada)
                              .where(EventoComissao.comanda_id == comanda))) == comissoes_originais
        assert db.get(Comanda, UUID(avulsa['id'])).cliente_id == s['client']

    assert enviar(api, s, decisao(s, 'desfazer', resposta['versao']), ator='recepcao')[0] == 403
    assert enviar(api, s, decisao(s, 'desfazer', resposta['versao']))[0] == 200
    assert {str(s['client']), str(s['presencial'])} <= ids_api(api, s, '/clientes/pesquisa')
    assert requisitar(api, perfil + '/atendimentos', s['admin'], filial_id=s['filial'])[1]['atendimentos'] == []
    with Session(s['engine']) as db:
        assert [x.acao for x in db.scalars(select(DecisaoCliente).order_by(DecisaoCliente.registrado_em))] == [
            'encaminhar', 'associar', 'desfazer',
        ]
        assert db.get(Comanda, UUID(avulsa['id'])).cliente_id == s['client']
        assert db.get(Comanda, comanda).cliente_id == s['presencial']


def test_pessoas_diferentes_somem_da_fila_e_reabrem_enquanto_seletores_separam(api, duplicata):
    s = duplicata
    filtros = dict(filial_id=s['filial'])
    dados = decisao(s, 'diferentes')
    assert enviar(api, s, dados, ator='user')[0] == 403
    codigo, diferente = enviar(api, s, dados)
    assert codigo == 200 and diferente['estado'] == 'diferentes'
    assert requisitar(api, '/clientes/duplicidades', s['recepcao'], **filtros) == (200, [])
    assert {str(s['client']), str(s['presencial'])} <= ids_api(api, s, '/clientes/pesquisa')
    assert enviar(api, s, decisao(s, 'reabrir', diferente['versao'], justificativa='  '))[0] == 422
    assert enviar(api, s, decisao(s, 'reabrir', diferente['versao'], justificativa='Nova conferência'))[0] == 200
    assert len(requisitar(api, '/clientes/duplicidades', s['admin'], **filtros)[1]) == 1


def test_bloqueia_duas_contas_e_pares_de_outra_filial(api, pg, duplicata):
    from app.models import Cliente, ContaPortalCliente

    s = duplicata
    remoto = cadastrar(api, s, 'Ficha externa', TELEFONE, filial=s['second'])
    assert enviar(api, s, decisao(s, cliente_b=remoto))[0] == 404
    assert enviar(api, s, decisao(s), ator='recepcao', filial=s['second'])[0] == 403
    with Session(pg) as db, db.begin():
        c = db.get(Cliente, s['presencial'])
        c.email, c.conta_ativada, c.senha_hash = 'segunda@example.com', True, 'hash-teste'
        db.add(ContaPortalCliente(cliente_id=c.id, email_confirmado=c.email, verificado_em=datetime.now(timezone.utc)))
    assert enviar(api, s, decisao(s))[0] == 422


def test_decisoes_concorrentes_respeitam_versao_e_trilha(duplicata):
    from app.models import DecisaoCliente, Usuario
    from app.schemas.duplicidade_cliente import RevisaoClienteEntrada
    from app.services.duplicidade_cliente import decidir
    from app.services.errors import ConflitoEstadoAgendamento

    s = duplicata
    barreira = Barrier(2, timeout=10)
    def decidir_junto(acao):
        with Session(s['engine']) as db:
            ator = db.get(Usuario, s['admin'])
            barreira.wait()
            try:
                decidir(db, ator, s['filial'], RevisaoClienteEntrada(**decisao(s, acao)))
                return 'ok'
            except ConflitoEstadoAgendamento:
                return 'conflito'
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(decidir_junto, ['associar', 'diferentes'])) == ['conflito', 'ok']
    with Session(s['engine']) as db:
        assert db.query(DecisaoCliente).count() == 1


def test_grupo_sem_cadeias_e_sem_pares_marcados_como_diferentes(api, duplicata):
    s = duplicata
    terceiro = cadastrar(api, s, 'Terceira ficha', TELEFONE)
    associado = enviar(api, s, decisao(s))[1]
    assert associado['principal_id'] == str(s['client'])
    assert enviar(api, s, decisao(s, cliente_a=str(s['presencial']), cliente_b=terceiro))[0] == 422
    codigo, diferente = enviar(api, s, decisao(
        s, 'diferentes', cliente_a=str(s['presencial']), cliente_b=terceiro,
    ))
    assert codigo == 200
    assert enviar(api, s, decisao(s, cliente_b=terceiro))[0] == 422
    assert enviar(api, s, decisao(s, 'reabrir', diferente['versao'], cliente_a=str(s['presencial']),
                                  cliente_b=terceiro))[0] == 200
    assert enviar(api, s, decisao(s, cliente_b=terceiro))[0] == 200
    assert ids_api(api, s, '/clientes/pesquisa') == {str(s['client'])}


def test_migracao_protege_a_trilha_de_auditoria(pg):
    with pg.connect() as db:
        assert db.scalar(text("""SELECT relrowsecurity FROM pg_class
                                 WHERE oid='public.clientes_decisoes'::regclass"""))
        assert db.scalar(text("""SELECT has_table_privilege('relaxabarber_runtime',
                                  'public.clientes_decisoes','INSERT')"""))
        for papel in ('anon', 'authenticated', 'service_role'):
            assert not db.scalar(text("""SELECT has_any_column_privilege(:papel,
                                         'public.clientes_decisoes','SELECT,INSERT,UPDATE')"""), {'papel': papel})
        for permissao in ('UPDATE', 'DELETE', 'TRUNCATE'):
            assert not db.scalar(text("""SELECT has_table_privilege('relaxabarber_runtime',
                    'public.clientes_decisoes', :permissao)"""), {'permissao': permissao})
