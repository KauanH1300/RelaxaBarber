"""Serviços reais, concorrência e falhas somente no PostgreSQL Docker descartável."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from test_financeiro_persistencia import data, legado, financeiro
from test_cancelamento_etapa_g import wait_for_lock


@pytest.fixture
def caso(pg, financeiro):
    from app.models import Usuario, PerfilEnum, UsuarioFilial, Filial
    with Session(pg) as db:
        atores = {"barbeiro": financeiro["user"], "outro": financeiro["other"]}
        for perfil in ("admin", "recepcao", "barbeiro_chefe"):
            usuario = Usuario(nome=perfil, email=f"{perfil}@financeiro.example.test",
                              senha_hash="ficticio", perfil=PerfilEnum(perfil))
            db.add(usuario)
            db.flush()
            db.add(UsuarioFilial(usuario_id=usuario.id, filial_id=financeiro["filial"]))
            atores[perfil] = usuario.id
        filial = db.get(Filial, financeiro["filial"])
        outra = Filial(nome="Outra ficticia", empresa_id=filial.empresa_id)
        db.add(outra)
        db.commit()
        return financeiro | {"atores": atores, "outra_filial": outra.id}


def ator(db, s, perfil="recepcao"):
    from app.models import Usuario
    return db.get(Usuario, s["atores"][perfil])


def pagar(db, s, perfil="recepcao", **mudancas):
    from app.models import PagamentoComanda
    from app.services.financeiro import fechar_comanda, PagamentoRegistrado
    dados = dict(valor=Decimal("30.50"), forma="pix",
        recebido_em=datetime.now(timezone.utc) - timedelta(minutes=1))
    chave = mudancas.pop('chave_idempotencia', uuid4())
    filial = mudancas.pop('filial_id', None)
    dados.update(mudancas)
    fechar_comanda(s['comanda'], pagamentos=[dados | {'confirmado': True}],
        chave_idempotencia=chave, filial_id=filial, db=db, usuario=ator(db, s, perfil))
    p = db.scalar(select(PagamentoComanda).where(PagamentoComanda.comanda_id == s['comanda']).order_by(PagamentoComanda.registrado_em.desc()))
    return PagamentoRegistrado(**{campo: getattr(p, campo) for campo in PagamentoRegistrado.__dataclass_fields__})


def historico(db, s, perfil='recepcao', **mudancas):
    """Fixture explícita de lançamentos anteriores à política integral, sem endpoint."""
    from app.models import PagamentoComanda
    from app.services.financeiro import PagamentoRegistrado
    from app.services.regras_financeiras import fingerprint
    dados = dict(valor=Decimal('10.00'), forma='pix',
        recebido_em=datetime.now(timezone.utc) - timedelta(minutes=1))
    chave = mudancas.pop('chave_idempotencia', uuid4())
    dados.update(mudancas)
    p = PagamentoComanda(comanda_id=s['comanda'], filial_id=s['filial'],
        registrado_por=s['atores'][perfil], chave_idempotencia=chave,
        fingerprint=fingerprint('pagamento', comanda_id=s['comanda'], **dados), **dados)
    db.add(p); db.flush(); db.refresh(p)
    resultado = PagamentoRegistrado(**{campo: getattr(p, campo) for campo in PagamentoRegistrado.__dataclass_fields__})
    db.commit()
    return resultado


def estornar(db, s, pagamento, **mudancas):
    from app.services.financeiro import registrar_estorno
    perfil = mudancas.pop("perfil", "admin")
    dados = dict(pagamento_id=pagamento.id, valor=Decimal("1.00"), motivo="Correção ficticia",
        efetivado_em=datetime.now(timezone.utc) - timedelta(seconds=1), chave_idempotencia=uuid4())
    dados.update(mudancas)
    return registrar_estorno(s["comanda"], db=db, usuario=ator(db, s, perfil), **dados)


def fechar(db, s, perfil="recepcao", **mudancas):
    from app.services.financeiro import fechar_comanda
    dados = dict(chave_idempotencia=uuid4()) | mudancas
    return fechar_comanda(s["comanda"], db=db, usuario=ator(db, s, perfil), **dados)


def consultar(db, s, perfil="recepcao", **mudancas):
    from app.services.financeiro import consultar_situacao
    return consultar_situacao(s["comanda"], db, ator(db, s, perfil), **mudancas)


def contagens(pg):
    with pg.connect() as conn:
        return tuple(conn.scalar(text(f"SELECT count(*) FROM {t}")) for t in
            ("pagamentos_comanda", "estornos_pagamento", "fechamentos_financeiros_comanda"))


def test_parciais_multiplas_formas_total_dos_itens_e_fechamento_explicito(pg, caso):
    from app.services.financeiro_errors import SaldoInsuficiente
    with pg.begin() as conn:
        conn.execute(text("UPDATE comandas SET valor_total=99999 WHERE id=:comanda"), caso)
    with Session(pg) as db:
        with pytest.raises(SaldoInsuficiente):
            pagar(db, caso, valor=Decimal('15.00'))
        assert contagens(pg) == (0, 0, 0)
        pagamentos = [dict(valor=Decimal(v), forma=f, confirmado=True,
            recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1))
            for v,f in [('5','dinheiro'),('5','pix'),('5','debito'),('15.50','credito')]]
        f = fechar(db, caso, pagamentos=pagamentos)
        assert f.total == f.recebido_liquido == Decimal('30.50')
        assert consultar(db, caso).situacao == 'fechado'
    assert contagens(pg) == (4, 0, 1)


@pytest.mark.parametrize("valor", [Decimal("0"), Decimal("-1"), Decimal("30.51"), Decimal("NaN"), Decimal("1.001"), 10.0])
def test_valores_invalidos_ou_excedentes_sem_escrita(pg, caso, valor):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida, SaldoInsuficiente
    with Session(pg) as db:
        with pytest.raises((EntradaFinanceiraInvalida, SaldoInsuficiente)):
            pagar(db, caso, valor=valor)
        assert db.scalar(text("SELECT 1")) == 1
    assert contagens(pg) == (0, 0, 0)


def test_saldo_pendente_impede_fechamento(pg, caso):
    from app.services.financeiro_errors import SaldoInsuficiente
    with Session(pg) as db:
        historico(db, caso)
        with pytest.raises(SaldoInsuficiente):
            fechar(db, caso)
    assert contagens(pg) == (1, 0, 0)


def test_zero_aguarda_fluxo_proprio_de_gratuidade(pg, caso):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel, EntradaFinanceiraInvalida
    with pg.begin() as conn:
        conn.execute(text("UPDATE itens_comanda SET preco_unitario=0 WHERE comanda_id=:comanda"), caso)
    with Session(pg) as db:
        with pytest.raises(EstadoFinanceiroIncompativel):
            fechar(db, caso)
        with pytest.raises(EntradaFinanceiraInvalida):
            fechar(db, caso, motivo=" \n ")
        with pytest.raises(EstadoFinanceiroIncompativel):
            fechar(db, caso, motivo="Cortesia autorizada")
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize("operacao", ["pagamento", "fechamento"])
def test_legado_nao_e_cobrado_nem_ativado(pg, legado, operacao):
    from app.models import Usuario
    from app.services import financeiro as f
    from app.services.financeiro_errors import HistoricoFinanceiroNaoVerificado
    with Session(pg) as db:
        usuario = db.get(Usuario, legado["user"])
        resumo = f.consultar_situacao(legado["comanda"], db, usuario)
        assert resumo.situacao == "nao_verificado" and resumo.saldo is None and resumo.recebido_liquido is None
        with pytest.raises(HistoricoFinanceiroNaoVerificado):
            if operacao == "pagamento":
                f.registrar_pagamento(legado["comanda"], db=db, usuario=usuario, valor=Decimal("1"),
                    forma="pix", recebido_em=datetime.now(timezone.utc), chave_idempotencia=uuid4())
            else:
                f.fechar_comanda(legado["comanda"], db=db, usuario=usuario, chave_idempotencia=uuid4())
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM controles_financeiros_comanda")) == 0
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize("estado,comanda", [("pendente", "pendente"),
    ("cancelado", "cancelada"), ("concluido", "pendente")])
def test_elegibilidade_financeira_independente_de_conclusao(pg, caso, estado, comanda):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with pg.begin() as conn:
        conn.execute(text("UPDATE agendamentos SET status=:status"), {"status": estado})
        conn.execute(text("UPDATE comandas SET status=:status"), {"status": comanda})
    with Session(pg) as db:
        with pytest.raises(EstadoFinanceiroIncompativel):
            pagar(db, caso)
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize("perfil", ["admin", "recepcao", "barbeiro", "barbeiro_chefe"])
def test_perfis_operam_proprias_sem_ampliar_consulta(pg, caso, perfil):
    # Para o chefe, tornar o profissional da comanda chefe em vez de trocar a comanda.
    if perfil == "barbeiro_chefe":
        with pg.begin() as conn:
            conn.execute(text("UPDATE usuarios SET perfil='BARBEIRO_CHEFE' WHERE id=:user"), caso)
        caso["atores"][perfil] = caso["user"]
    with Session(pg) as db:
        pagar(db, caso, perfil=perfil, valor=Decimal("30.50"))
        assert consultar(db, caso, perfil=perfil).saldo == 0
    assert contagens(pg) == (1, 0, 1)


@pytest.mark.parametrize("perfil", ["outro", "barbeiro_chefe"])
@pytest.mark.parametrize("operacao", ["consulta", "pagamento", "fechamento"])
def test_barbeiros_nao_acessam_financeiro_de_outros(pg, caso, perfil, operacao):
    from app.services.financeiro_errors import ComandaFinanceiraNaoEncontrada
    with Session(pg) as db:
        with pytest.raises(ComandaFinanceiraNaoEncontrada):
            {"consulta": consultar, "pagamento": pagar, "fechamento": fechar}[operacao](db, caso, perfil=perfil)
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize("perfil", ["recepcao", "barbeiro", "barbeiro_chefe"])
def test_estorno_exclusivo_admin(pg, caso, perfil):
    from app.services.financeiro_errors import AcessoFinanceiroNegado
    with Session(pg) as db:
        p = historico(db, caso)
        with pytest.raises(AcessoFinanceiroNegado):
            estornar(db, caso, p, perfil=perfil)
    assert contagens(pg) == (1, 0, 0)


@pytest.mark.parametrize("alvo", ["vinculo", "usuario", "filial", "empresa"])
def test_revogacao_impede_operacao_e_replay(pg, caso, alvo):
    from app.services.financeiro_errors import AcessoFinanceiroNegado, ComandaFinanceiraNaoEncontrada
    chave = uuid4()
    efetiva = datetime.now(timezone.utc) - timedelta(minutes=1)
    with Session(pg) as db:
        pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva)
    with pg.begin() as conn:
        if alvo == "vinculo":
            conn.execute(text("UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id"), {"id": caso["atores"]["recepcao"]})
        elif alvo == "usuario":
            conn.execute(text("UPDATE usuarios SET ativo=false WHERE id=:id"), {"id": caso["atores"]["recepcao"]})
        elif alvo == "filial":
            conn.execute(text("UPDATE filiais SET ativa=false WHERE id=:filial"), caso)
        else:
            conn.execute(text("UPDATE empresas SET ativa=false"))
    with Session(pg) as db:
        with pytest.raises((AcessoFinanceiroNegado, ComandaFinanceiraNaoEncontrada)):
            pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva)
    assert contagens(pg) == (1, 0, 1)


def test_filial_divergente_e_usuario_sem_vinculo(pg, caso):
    from app.services.financeiro_errors import ComandaFinanceiraNaoEncontrada
    with Session(pg) as db:
        with pytest.raises(ComandaFinanceiraNaoEncontrada):
            pagar(db, caso, filial_id=caso["outra_filial"])
    with pg.begin() as conn:
        # Recepção continua vinculada a uma filial ativa, mas não à da comanda.
        conn.execute(text("UPDATE usuario_filiais SET filial_id=:outra_filial WHERE usuario_id=:id"),
                     caso | {"id": caso["atores"]["recepcao"]})
    with Session(pg) as db:
        with pytest.raises(ComandaFinanceiraNaoEncontrada):
            consultar(db, caso)
    assert contagens(pg) == (0, 0, 0)


@pytest.mark.parametrize("dias,perfil,permitido", [(6, "recepcao", True), (8, "recepcao", False),
    (8, "barbeiro", False), (100, "admin", True), (-1, "admin", False), (-1, "recepcao", False)])
def test_datas_retroativas_e_futuras(pg, caso, dias, perfil, permitido):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    efetiva = datetime.now(timezone.utc) - timedelta(days=dias, minutes=1)
    with Session(pg) as db:
        if permitido:
            p = pagar(db, caso, perfil=perfil, recebido_em=efetiva)
            assert p.recebido_em == efetiva
            assert p.registrado_por == caso["atores"][perfil]
            assert p.registrado_em > efetiva
        else:
            with pytest.raises(EntradaFinanceiraInvalida):
                pagar(db, caso, perfil=perfil, recebido_em=efetiva)
    assert contagens(pg) == (int(permitido), 0, int(permitido))


def test_timestamp_sem_fuso_e_recusado(pg, caso):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with Session(pg) as db:
        with pytest.raises(EntradaFinanceiraInvalida):
            pagar(db, caso, recebido_em=datetime(2026, 1, 1))
    assert contagens(pg) == (0, 0, 0)


def test_reenvio_identico_apos_fechamento_e_janela_expirada(pg, caso, monkeypatch):
    from app.services import financeiro as f
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira
    chave = uuid4()
    efetiva = datetime.now(timezone.utc) - timedelta(minutes=1)
    with Session(pg) as db:
        p = pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva)
        monkeypatch.setattr(f, '_agora', lambda db: pytest.fail('Replay não revalida janela'))
        assert pagar(db, caso, valor=Decimal('30.500'), chave_idempotencia=chave, recebido_em=efetiva) == p
        with pytest.raises(ConflitoIdempotenciaFinanceira):
            pagar(db, caso, valor=Decimal('1'), chave_idempotencia=chave, recebido_em=efetiva)
    assert contagens(pg) == (1,0,1)


def test_estorno_parcial_limite_e_idempotencia_preservam_original(pg, caso):
    from app.services.financeiro_errors import LimiteEstornoExcedido, ConflitoIdempotenciaFinanceira
    efetiva = datetime.now(timezone.utc) - timedelta(seconds=1)
    chave = uuid4()
    with Session(pg) as db:
        p = historico(db, caso, valor=Decimal("30.50"))
        e = estornar(db, caso, p, valor=Decimal("5"), efetivado_em=efetiva, chave_idempotencia=chave)
        assert estornar(db, caso, p, valor=Decimal("5.00"), efetivado_em=efetiva, chave_idempotencia=chave) == e
        assert consultar(db, caso).saldo == Decimal("5")
        with pytest.raises(ConflitoIdempotenciaFinanceira):
            estornar(db, caso, p, valor=Decimal("4"), efetivado_em=efetiva, chave_idempotencia=chave)
        with pytest.raises(LimiteEstornoExcedido):
            estornar(db, caso, p, valor=Decimal("25.51"))
        estornar(db, caso, p, valor=Decimal("25.50"))
        assert consultar(db, caso).recebido_liquido == 0
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT valor FROM pagamentos_comanda")) == Decimal("30.50")
    assert contagens(pg) == (1, 2, 0)


def test_estorno_bloqueado_apos_fechamento_e_novo_pagamento_tambem(pg, caso):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with Session(pg) as db:
        p = historico(db, caso, valor=Decimal("30.50"))
        fechar(db, caso)
        with pytest.raises(EstadoFinanceiroIncompativel):
            estornar(db, caso, p)
        with pytest.raises(EstadoFinanceiroIncompativel):
            pagar(db, caso)
    assert contagens(pg) == (1, 0, 1)


@pytest.mark.parametrize("alteracoes", [{"motivo": " \t "}, {"efetivado_em": datetime(2000, 1, 1, tzinfo=timezone.utc)},
    {"pagamento_id": uuid4()}, {"efetivado_em": datetime.now(timezone.utc) + timedelta(days=1)}])
def test_estorno_valida_motivo_origem_e_data(pg, caso, alteracoes):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida, ComandaFinanceiraNaoEncontrada
    with Session(pg) as db:
        p = historico(db, caso)
        with pytest.raises((EntradaFinanceiraInvalida, ComandaFinanceiraNaoEncontrada)):
            estornar(db, caso, p, **alteracoes)
    assert contagens(pg) == (1, 0, 0)


def test_consulta_coerente_nao_faz_commit_nem_dml(pg, caso):
    from sqlalchemy import event
    statements = []
    class Contada(Session):
        def commit(self):
            pytest.fail("Consulta não deve confirmar transação")
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())
    event.listen(pg, "before_cursor_execute", capture)
    try:
        with Contada(pg) as db:
            assert consultar(db, caso).saldo == Decimal("30.50")
    finally:
        event.remove(pg, "before_cursor_execute", capture)
    assert not set(statements) & {"INSERT", "UPDATE", "DELETE"}


def test_commit_unico_por_operacao_e_sem_leitura_posterior(pg, caso):
    from sqlalchemy import event
    bloqueio = {'ativo': False}
    def guardar_sql(conn, cursor, statement, parameters, context, executemany):
        assert not bloqueio['ativo'], 'SQL após commit'
    class Contada(Session):
        commits = 0
        def commit(self):
            super().commit()
            self.commits += 1
            bloqueio['ativo'] = True
    event.listen(pg, 'before_cursor_execute', guardar_sql)
    try:
        with Contada(pg) as db:
            fechar(db, caso, pagamentos=[dict(valor=Decimal('30.50'),forma='pix',
                recebido_em=datetime.now(timezone.utc)-timedelta(minutes=1),confirmado=True)])
            assert db.commits == 1
    finally:
        event.remove(pg, 'before_cursor_execute', guardar_sql)


@pytest.mark.parametrize("confirmar", [False, True])
def test_commit_indeterminado_reenvio_mesma_chave_nao_duplica(pg, caso, confirmar):
    from app.services.persistencia import ConfirmacaoIndeterminada
    chave = uuid4()
    efetiva = datetime.now(timezone.utc) - timedelta(minutes=1)
    class Incerta(Session):
        def commit(self):
            if confirmar:
                super().commit()
            raise OperationalError(None, {}, SimpleNamespace(pgcode="08006"), connection_invalidated=True)
    with Incerta(pg) as db:
        with pytest.raises(ConfirmacaoIndeterminada):
            pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva)
    assert contagens(pg) == (int(confirmar), 0, int(confirmar))
    with Session(pg) as db:
        p = pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva)
        assert pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva) == p
    assert contagens(pg) == (1, 0, 1)


def test_abortamento_confirmado_rollback_integral(pg, caso):
    from app.services.persistencia import TransacaoAbortada
    class Abortada(Session):
        def commit(self):
            raise OperationalError(None, {}, SimpleNamespace(pgcode="40001"))
    with Abortada(pg) as db:
        with pytest.raises(TransacaoAbortada):
            pagar(db, caso)
        assert db.scalar(text("SELECT 1")) == 1
    assert contagens(pg) == (0, 0, 0)


def test_falha_na_leitura_pre_commit_reverte_insert(pg, caso):
    from app.services.persistencia import BancoIndisponivel, ConfirmacaoIndeterminada
    class SemLeitura(Session):
        def refresh(self, *args, **kwargs):
            raise OperationalError("SELECT ficticio", {}, SimpleNamespace(pgcode="08006"))
    with SemLeitura(pg) as db:
        with pytest.raises(BancoIndisponivel) as erro:
            pagar(db, caso)
        assert not isinstance(erro.value, ConfirmacaoIndeterminada)
        assert db.scalar(text("SELECT 1")) == 1
    assert contagens(pg) == (0, 0, 0)


def test_timeout_de_lock_nao_lanca_e_reenvio_pode_executar_uma_vez(pg, caso):
    from app.models import Agendamento
    from app.services.persistencia import FalhaPersistencia
    chave = uuid4()
    efetiva = datetime.now(timezone.utc) - timedelta(minutes=1)
    pronto = Event()
    pid = []
    def esperar():
        with Session(pg) as db:
            db.execute(text("SET LOCAL lock_timeout='300ms'"))
            pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            pronto.set()
            with pytest.raises(FalhaPersistencia):
                pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva)
            assert db.scalar(text("SELECT 1")) == 1
    with Session(pg) as bloqueadora, ThreadPoolExecutor(max_workers=1) as pool:
        bloqueadora.scalar(select(Agendamento).where(Agendamento.id == caso["agendamento"]).with_for_update())
        trabalho = pool.submit(esperar)
        try:
            assert pronto.wait(5)
            wait_for_lock(pg, pid[0])
            trabalho.result(timeout=5)
        finally:
            bloqueadora.rollback()
    assert contagens(pg) == (0, 0, 0)
    with Session(pg) as db:
        p = pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva)
        assert pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva) == p
    assert contagens(pg) == (1, 0, 1)


def disputar(pg, primeira, segunda):
    """Primeiro serviço mantém locks até COMMIT; comprova espera real do segundo."""
    pronta, liberar, iniciou = Event(), Event(), Event()
    pid = []
    class Pausada(Session):
        def commit(self):
            pronta.set()
            assert liberar.wait(10)
            super().commit()
    def executar_primeira():
        with Pausada(pg) as db:
            db.execute(text("SET LOCAL statement_timeout='12s'"))
            return primeira(db)
    def executar_segunda():
        from app.models import Comanda
        with Session(pg) as db:
            db.execute(text("SET LOCAL statement_timeout='12s'"))
            # Identity map deliberadamente anterior ao COMMIT concorrente.
            precarregadas = list(db.scalars(select(Comanda)))
            assert precarregadas
            pid.append(db.scalar(text("SELECT pg_backend_pid()")))
            iniciou.set()
            try:
                return segunda(db)
            except Exception as exc:
                from app.services.financeiro_errors import ErroFinanceiro
                if not isinstance(exc, ErroFinanceiro):
                    raise
                return exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        um = pool.submit(executar_primeira)
        try:
            assert pronta.wait(10)
            dois = pool.submit(executar_segunda)
            assert iniciou.wait(5)
            wait_for_lock(pg, pid[0])
        finally:
            liberar.set()
        return um.result(timeout=15), dois.result(timeout=15)


@pytest.mark.parametrize("modo", ["mesma_chave", "conteudo_diferente", "excedente"])
def test_dois_operadores_pagando_concorrentemente(pg, caso, modo):
    from app.services.financeiro_errors import ConflitoIdempotenciaFinanceira, EstadoFinanceiroIncompativel
    chave = uuid4()
    efetiva = datetime.now(timezone.utc) - timedelta(minutes=1)
    um, dois = disputar(pg,
        lambda db: pagar(db, caso, chave_idempotencia=chave, recebido_em=efetiva),
        lambda db: pagar(db, caso, perfil='admin', valor=Decimal('10') if modo=='conteudo_diferente' else Decimal('30.50'),
            chave_idempotencia=chave if modo!='excedente' else uuid4(), recebido_em=efetiva))
    if modo == 'mesma_chave':
        assert um == dois and dois.registrado_por == caso['atores']['recepcao']
    else:
        assert isinstance(dois, ConflitoIdempotenciaFinanceira if modo=='conteudo_diferente' else EstadoFinanceiroIncompativel)
    assert contagens(pg) == (1,0,1)


@pytest.mark.parametrize("primeira", ["fechamento", "estorno"])
def test_estorno_concorrente_com_fechamento(pg, caso, primeira):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel, SaldoInsuficiente
    with Session(pg) as db:
        p = historico(db, caso, valor=Decimal("30.50"))
    if primeira == "fechamento":
        _, segundo = disputar(pg, lambda db: fechar(db, caso), lambda db: estornar(db, caso, p))
        assert isinstance(segundo, EstadoFinanceiroIncompativel)
        assert contagens(pg) == (1, 0, 1)
    else:
        _, segundo = disputar(pg, lambda db: estornar(db, caso, p), lambda db: fechar(db, caso))
        assert isinstance(segundo, SaldoInsuficiente)
        assert contagens(pg) == (1, 1, 0)


def test_estornos_concorrentes_nao_excedem_original(pg, caso):
    from app.services.financeiro_errors import LimiteEstornoExcedido
    with Session(pg) as db:
        p = historico(db, caso)
    _, segundo = disputar(pg,
        lambda db: estornar(db, caso, p, valor=Decimal("7")),
        lambda db: estornar(db, caso, p, valor=Decimal("7")))
    assert isinstance(segundo, LimiteEstornoExcedido)
    assert contagens(pg) == (1, 1, 0)


def test_isolamento_incompativel_e_recusado(pg, caso):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    engine = pg.execution_options(isolation_level="REPEATABLE READ")
    with Session(engine) as db:
        with pytest.raises(EntradaFinanceiraInvalida):
            pagar(db, caso)
    assert contagens(pg) == (0, 0, 0)


def test_servicos_com_login_runtime_restrito(pg, runtime_pg, caso):
    with Session(pg) as db:
        p = historico(db, caso, valor=Decimal('30.50'))
    with Session(runtime_pg) as db:
        estornar(db, caso, p, valor=Decimal('1'))
        pagar(db, caso, valor=Decimal('1'))
        assert consultar(db, caso).saldo == 0
    assert contagens(pg) == (2,1,1)


@pytest.mark.parametrize("alvo", ["vinculo", "usuario"])
def test_revogacao_concorrente_primeiro_impede_pagamento(pg, caso, alvo):
    from app.services.financeiro_errors import ComandaFinanceiraNaoEncontrada, AcessoFinanceiroNegado
    def revogar(db):
        if alvo == "vinculo":
            db.execute(text("UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id"),
                       {"id": caso["atores"]["recepcao"]})
        else:
            db.execute(text("UPDATE usuarios SET ativo=false WHERE id=:id"),
                       {"id": caso["atores"]["recepcao"]})
        db.commit()
    _, resultado = disputar(pg, revogar, lambda db: pagar(db, caso))
    assert isinstance(resultado, (ComandaFinanceiraNaoEncontrada, AcessoFinanceiroNegado))
    assert contagens(pg) == (0, 0, 0)


def test_pagamento_primeiro_mantem_autorizacao_ate_commit(pg, caso):
    def revogar(db):
        db.execute(text("UPDATE usuario_filiais SET ativo=false WHERE usuario_id=:id"),
                   {"id": caso["atores"]["recepcao"]})
        db.commit()
    p, _ = disputar(pg, lambda db: pagar(db, caso), revogar)
    assert p.valor == Decimal("30.50")
    assert contagens(pg) == (1, 0, 1)
    with pg.connect() as conn:
        assert not conn.scalar(text("SELECT ativo FROM usuario_filiais WHERE usuario_id=:id"),
                               {"id": caso["atores"]["recepcao"]})


@pytest.mark.parametrize("mesma_chave", [True, False])
def test_fechamentos_concorrentes_nao_duplicam(pg, caso, mesma_chave):
    from app.services.financeiro_errors import EstadoFinanceiroIncompativel
    with Session(pg) as db:
        historico(db, caso, valor=Decimal("30.50"))
    chave = uuid4()
    um, dois = disputar(pg,
        lambda db: fechar(db, caso, chave_idempotencia=chave),
        lambda db: fechar(db, caso, perfil="admin", chave_idempotencia=chave if mesma_chave else uuid4()))
    if mesma_chave:
        assert um == dois
    else:
        assert isinstance(dois, EstadoFinanceiroIncompativel)
    assert contagens(pg) == (1, 0, 1)


@pytest.mark.parametrize("sql", [
    "UPDATE itens_comanda SET quantidade=0", "UPDATE itens_comanda SET preco_unitario=-1",
    "UPDATE itens_comanda SET quantidade=100000000",
])
def test_itens_invalidos_impedem_novos_recebimentos(pg, caso, sql):
    from app.services.financeiro_errors import DadosFinanceirosInconsistentes
    with pg.begin() as conn:
        conn.execute(text(sql))
    with Session(pg) as db:
        with pytest.raises(DadosFinanceirosInconsistentes):
            pagar(db, caso)
    assert contagens(pg) == (0, 0, 0)


def test_nao_acessa_comanda_ou_pagamento_de_outra_filial(pg, caso):
    from test_financeiro_persistencia import criar_comanda
    from app.services.financeiro_errors import ComandaFinanceiraNaoEncontrada
    with pg.begin() as conn:
        conn.execute(text("INSERT INTO usuario_filiais(id,usuario_id,filial_id) VALUES (:id,:user,:outra_filial)"),
                     caso | {"id": uuid4()})
        outra = criar_comanda(conn, caso | {"filial": caso["outra_filial"]}, dia="2099-02-01", controle=True)
        outra["atores"] = caso["atores"]
    with Session(pg) as db:
        with pytest.raises(ComandaFinanceiraNaoEncontrada):
            pagar(db, outra)  # recepção da primeira filial
        p = historico(db, outra, perfil="admin")
        with pytest.raises(ComandaFinanceiraNaoEncontrada):
            estornar(db, caso, p)  # pagamento verdadeiro, mas de outra comanda/filial
        with pytest.raises(ComandaFinanceiraNaoEncontrada):
            pagar(db, outra, perfil="admin", filial_id=caso["filial"])
    with pg.begin() as conn:
        conn.execute(text("UPDATE filiais SET ativa=false WHERE id=:outra_filial"), caso)
    with Session(pg) as db:
        with pytest.raises(ComandaFinanceiraNaoEncontrada):
            estornar(db, outra, p)  # ADMIN também respeita disponibilidade do contexto
    assert contagens(pg) == (1, 0, 0)
