"""Regras financeiras puras, sem rede, engine ou valores vindos do frontend."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest


@pytest.fixture
def regras(isolated_runtime):
    from app.services import regras_financeiras
    return regras_financeiras


@pytest.mark.parametrize("valor", ["0.01", "1.000", "12.30", "99999999.99"])
def test_moeda_exata(regras, valor):
    assert regras.valor_monetario(Decimal(valor)) == Decimal(valor)
    assert regras.valor_monetario(Decimal(valor)).as_tuple().exponent == -2


@pytest.mark.parametrize("valor", [0.1, 1, "1.00", None, Decimal("0"), Decimal("-1"),
    Decimal("NaN"), Decimal("Infinity"), Decimal("0.001"), Decimal("100000000")])
def test_moeda_invalida(regras, valor):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with pytest.raises(EntradaFinanceiraInvalida):
        regras.valor_monetario(valor)
    assert regras.valor_monetario(Decimal("0"), permitir_zero=True) == Decimal("0.00")


@pytest.mark.parametrize("idade,admin,permitido", [
    (timedelta(0), False, True), (timedelta(days=7), False, True),
    (timedelta(days=7, microseconds=1), False, False),
    (timedelta(days=365), True, True), (timedelta(days=365), False, False),
    (timedelta(microseconds=-1), True, False), (timedelta(microseconds=-1), False, False),
])
def test_janela_continua_inclusiva_e_futuro(regras, idade, admin, permitido):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    agora = datetime(2026, 11, 12, 12, tzinfo=ZoneInfo("America/Recife"))
    efetiva = (agora - idade).astimezone(timezone.utc)
    if permitido:
        regras.validar_janela(efetiva, agora, admin=admin)
    else:
        with pytest.raises(EntradaFinanceiraInvalida):
            regras.validar_janela(efetiva, agora, admin=admin)


@pytest.mark.parametrize("valor", [None, "2026-11-12", datetime(2026, 11, 12)])
def test_timezone_obrigatorio(regras, valor):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with pytest.raises(EntradaFinanceiraInvalida):
        regras.data_efetiva(valor)


def test_canonicalizacao_de_data_e_decimal(regras):
    ident = uuid4()
    data = datetime(2026, 11, 12, 12, tzinfo=ZoneInfo("America/Recife"))
    um = regras.fingerprint("pagamento", id=ident, valor=Decimal("1.0"), data=data)
    outro = regras.fingerprint("pagamento", data=data.astimezone(timezone.utc), valor=Decimal("1.00"), id=ident)
    assert um == outro and len(um) == 64
    assert um != regras.fingerprint("estorno", id=ident, valor=Decimal("1.0"), data=data)
    assert um != regras.fingerprint("pagamento", id=ident, valor=Decimal("1.01"), data=data)


@pytest.mark.parametrize("valor", [None, "", " \n\t ", 42])
def test_motivo_obrigatorio_auditavel(regras, valor):
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    with pytest.raises(EntradaFinanceiraInvalida):
        regras.motivo_auditavel(valor, obrigatorio=True)
    assert regras.motivo_auditavel("  Cortesia  ") == "Cortesia"


@pytest.mark.parametrize("situacao,op,comanda,erro", [
    ("nao_verificado", "concluido", "fechada", "HistoricoFinanceiroNaoVerificado"),
    ("fechado", "concluido", "fechada", "EstadoFinanceiroIncompativel"),
    ("aberto", "em_atendimento", "aberta", "EstadoFinanceiroIncompativel"),
    ("aberto", "cancelado", "cancelada", "EstadoFinanceiroIncompativel"),
    ("aberto", "concluido", "aberta", "EstadoFinanceiroIncompativel"),
])
def test_regras_de_estado(isolated_runtime, situacao, op, comanda, erro):
    from app.services import financeiro, financeiro_errors
    with pytest.raises(getattr(financeiro_errors, erro)):
        financeiro._permitir_nova_operacao(SimpleNamespace(situacao=situacao),
            SimpleNamespace(status=op), SimpleNamespace(status=comanda))


def test_sessao_suja_nao_e_confirmada_nem_descartada(isolated_runtime):
    from app.services.financeiro import _escrita
    from app.services.financeiro_errors import EntradaFinanceiraInvalida
    from unittest.mock import Mock
    db = Mock(new={object()}, dirty=set(), deleted=set())
    with pytest.raises(EntradaFinanceiraInvalida):
        with _escrita(db):
            pytest.fail("Não deve entrar na transação financeira")
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_resposta_nao_depende_de_sessao_apos_commit(isolated_runtime):
    from app.services.financeiro import ResumoFinanceiro
    resumo = ResumoFinanceiro(uuid4(), uuid4(), "nao_verificado", Decimal("10"), None, None, None, None)
    with pytest.raises(FrozenInstanceError):
        resumo.saldo = Decimal("10")
