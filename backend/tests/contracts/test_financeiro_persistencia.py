"""Modelos e DDL offline; sem engine real, .env ou rede."""
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest


@pytest.mark.parametrize("valor", ["0", "0.01", "12.30", "99999999.99", "1.000"])
def test_decimal_exato(isolated_runtime, valor):
    from app.models.financeiro import ValorFinanceiro
    assert ValorFinanceiro().process_bind_param(Decimal(valor), None) == Decimal(valor)


@pytest.mark.parametrize("valor", [0.1, 1, "1.00", Decimal("0.001"), Decimal("100000000"),
                                  Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_orm_recusa_float_arredondamento_e_nao_finitos(isolated_runtime, valor):
    from app.models.financeiro import ValorFinanceiro
    with pytest.raises(ValueError):
        ValorFinanceiro().process_bind_param(valor, None)


def test_estado_independente_sem_inferir_pagamento(models):
    from app.models import Comanda, ControleFinanceiroComanda, FechamentoFinanceiroComanda
    for operacional in ("pendente", "aberta", "fechada", "cancelada"):
        comanda = Comanda(status=operacional)
        assert comanda.situacao_financeira == "nao_verificado"
        comanda.controle_financeiro = ControleFinanceiroComanda(motivo="Ativação explícita")
        assert comanda.situacao_financeira == "aberto"
        comanda.controle_financeiro.fechamento = FechamentoFinanceiroComanda()
        assert comanda.situacao_financeira == "fechado"
        assert comanda.status == operacional


def test_cadeia_e_ddl_aditiva_com_protecao_de_historico(isolated_runtime):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["d93a7e2f610c"]
    revision = scripts.get_revision("head")
    assert revision.down_revision == "c82f6a1d904b"
    output = StringIO()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql", opts={
            "as_sql": True, "output_buffer": output})):
        revision.module.upgrade()
    sql = output.getvalue()
    assert sql.count("CREATE TABLE public.") == 4
    assert "INSERT INTO" not in sql.upper()
    assert "UPDATE public.comandas" not in sql
    assert "ON DELETE RESTRICT" in sql
    assert "BEFORE UPDATE OR DELETE OR TRUNCATE" in sql
    assert "clock_timestamp()" in sql
    assert "SECURITY DEFINER" not in sql
    assert "ALTER DEFAULT PRIVILEGES" not in sql
    assert "autocommit" not in sql.lower()
    output = StringIO()
    with Operations.context(MigrationContext.configure(dialect_name="postgresql", opts={
            "as_sql": True, "output_buffer": output})):
        revision.module.downgrade()
    sql = output.getvalue()
    assert sql.index("ACCESS EXCLUSIVE") < sql.index("Downgrade bloqueado") < sql.index("DROP TABLE")
