"""DDL e lançamentos fictícios somente no PostgreSQL descartável validado por conftest."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from test_concorrencia import data, insert
from test_modelagem_filiais import scripts, snapshot

REVISION = "d93a7e2f610c"
TABELAS = ("controles_financeiros_comanda", "pagamentos_comanda",
           "estornos_pagamento", "fechamentos_financeiros_comanda")


def migrar(conn, direcao):
    with Operations.context(MigrationContext.configure(conn)):
        getattr(scripts().get_revision(REVISION).module, direcao)()


def criar_comanda(conn, data, dia="2099-01-01", controle=False):
    ident = uuid4()
    agendamento = insert(conn, data, day=dia, status="concluido")
    s = data | {"comanda": ident, "agendamento": agendamento}
    conn.execute(text("""INSERT INTO comandas
        (id,filial_id,agendamento_id,cliente_id,barbeiro_id,status,valor_total,data_fechamento)
        VALUES (:comanda,:filial,:agendamento,:client,:user,'fechada',30.50,now())"""), s)
    conn.execute(text("""INSERT INTO itens_comanda
        (id,comanda_id,tipo,descricao,quantidade,preco_unitario)
        VALUES (:id,:comanda,'servico','Item ficticio',1,30.50)"""), s | {"id": uuid4()})
    if controle:
        ativar(conn, s)
    return s


def ativar(conn, s):
    conn.execute(text("""INSERT INTO controles_financeiros_comanda
        (comanda_id,filial_id,registrado_por,motivo) VALUES (:comanda,:filial,:user,'Controle ficticio')"""), s)


@pytest.fixture
def legado(pg, data):
    with pg.begin() as conn:
        return criar_comanda(conn, data)


@pytest.fixture
def financeiro(pg, legado):
    with pg.begin() as conn:
        ativar(conn, legado)
    return legado


def pagar(conn, s, **alteracoes):
    params = s | {"id": uuid4(), "valor": Decimal("10.00"), "forma": "pix",
                  "efetiva": datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
                  "registro": datetime(2000, 1, 1, tzinfo=timezone.utc),
                  "chave": uuid4(), "fingerprint": "a" * 64} | alteracoes
    conn.execute(text("""INSERT INTO pagamentos_comanda
        (id,comanda_id,filial_id,valor,forma,recebido_em,registrado_em,registrado_por,chave_idempotencia,fingerprint)
        VALUES (:id,:comanda,:filial,:valor,:forma,:efetiva,:registro,:user,:chave,:fingerprint)"""), params)
    return params


def estornar(conn, s, pagamento, **alteracoes):
    params = s | {"id": uuid4(), "pagamento": pagamento, "valor": Decimal("1.00"),
                  "motivo": "Estorno ficticio", "chave": uuid4(), "fingerprint": "b" * 64} | alteracoes
    conn.execute(text("""INSERT INTO estornos_pagamento
        (id,pagamento_id,comanda_id,filial_id,valor,motivo,efetivado_em,registrado_por,chave_idempotencia,fingerprint)
        VALUES (:id,:pagamento,:comanda,:filial,:valor,:motivo,now(),:user,:chave,:fingerprint)"""), params)
    return params


def fechar(conn, s, **alteracoes):
    params = s | {"total": Decimal("30.50"), "liquido": Decimal("30.50"),
                  "motivo": None, "chave": uuid4(), "fingerprint": "c" * 64} | alteracoes
    conn.execute(text("""INSERT INTO fechamentos_financeiros_comanda
        (comanda_id,filial_id,total,recebido_liquido,motivo,registrado_por,chave_idempotencia,fingerprint)
        VALUES (:comanda,:filial,:total,:liquido,:motivo,:user,:chave,:fingerprint)"""), params)


def test_modelos_correspondem_a_migracao(pg):
    from app.models import Base
    with pg.connect() as conn:
        actual = inspect(conn)
        for nome in TABELAS:
            tabela = Base.metadata.tables[nome]
            colunas = {c["name"]: c for c in actual.get_columns(nome)}
            assert set(colunas) == set(tabela.c.keys())
            for col in tabela.c:
                assert colunas[col.name]["nullable"] == col.nullable
                if col.name in ("valor", "total", "recebido_liquido"):
                    assert (colunas[col.name]["type"].precision, colunas[col.name]["type"].scale) == (10, 2)
            for metodo, esperadas in (
                (actual.get_check_constraints, {c.name for c in tabela.constraints if c.__class__.__name__ == "CheckConstraint"}),
                (actual.get_unique_constraints, {c.name for c in tabela.constraints if c.__class__.__name__ == "UniqueConstraint"}),
                (actual.get_foreign_keys, {c.name for c in tabela.foreign_key_constraints}),
            ):
                assert {c["name"] for c in metodo(nome)} == esperadas
            assert {i["name"] for i in actual.get_indexes(nome) if not i.get("duplicates_constraint")} == {i.name for i in tabela.indexes}
            assert all(fk["options"].get("ondelete") == "RESTRICT" for fk in actual.get_foreign_keys(nome))


def test_upgrade_downgrade_preservam_legado_e_revisao(pg, legado):
    # Volta ao predecessor sem histórico financeiro; depois aplica DDL real.
    with pg.begin() as conn:
        conn.execute(text("SET LOCAL ROLE rb_horarios_migrador"))
        antes = snapshot(conn)
        migrar(conn, "downgrade")
        contexto = MigrationContext.configure(conn)
        contexto.stamp(scripts(), "c82f6a1d904b")
    with pg.begin() as conn:
        conn.execute(text("SET LOCAL ROLE rb_horarios_migrador"))
        migrar(conn, "upgrade")
        MigrationContext.configure(conn).stamp(scripts(), REVISION)
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
        assert snapshot(conn) == antes
        assert all(conn.scalar(text(f"SELECT count(*) FROM {t}")) == 0 for t in TABELAS)
    from app.models import Comanda
    with Session(pg) as db:
        command = db.get(Comanda, legado["comanda"])
        assert command.status == "fechada"
        assert command.situacao_financeira == "nao_verificado"
    with pg.begin() as conn:
        conn.execute(text("SET LOCAL ROLE rb_horarios_migrador"))
        migrar(conn, "downgrade")
        MigrationContext.configure(conn).stamp(scripts(), "c82f6a1d904b")
        assert snapshot(conn) == antes
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "c82f6a1d904b"
        assert not set(TABELAS) & set(inspect(conn).get_table_names())


def test_upgrade_e_downgrade_sao_ddl_transacional(pg, legado):
    with pg.begin() as conn:
        migrar(conn, "downgrade")
        MigrationContext.configure(conn).stamp(scripts(), "c82f6a1d904b")
        antes = snapshot(conn)
    with pg.connect() as conn:
        tx = conn.begin()
        migrar(conn, "upgrade")
        MigrationContext.configure(conn).stamp(scripts(), REVISION)
        assert set(TABELAS) <= set(inspect(conn).get_table_names())
        tx.rollback()
    with pg.connect() as conn:
        assert not set(TABELAS) & set(inspect(conn).get_table_names())
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == "c82f6a1d904b"
        assert snapshot(conn) == antes
    with pg.begin() as conn:
        migrar(conn, "upgrade")
        MigrationContext.configure(conn).stamp(scripts(), REVISION)
    with pg.connect() as conn:
        tx = conn.begin()
        migrar(conn, "downgrade")
        MigrationContext.configure(conn).stamp(scripts(), "c82f6a1d904b")
        tx.rollback()
    with pg.connect() as conn:
        assert set(TABELAS) <= set(inspect(conn).get_table_names())
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == REVISION


def test_downgrade_bloqueia_mesmo_so_com_ativacao(pg, financeiro):
    with pytest.raises(DBAPIError, match="Downgrade bloqueado"):
        with pg.begin() as conn:
            migrar(conn, "downgrade")
    with pg.connect() as conn:
        assert set(TABELAS) <= set(inspect(conn).get_table_names())
        assert conn.scalar(text("SELECT count(*) FROM controles_financeiros_comanda")) == 1


@pytest.mark.parametrize("valor", [Decimal("0"), Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), Decimal("100000000")])
def test_pagamentos_invalidos_no_banco(pg, financeiro, valor):
    with pytest.raises(DBAPIError):
        with pg.begin() as conn:
            pagar(conn, financeiro, valor=valor)


@pytest.mark.parametrize("forma", ["dinheiro", "pix", "debito", "credito"])
def test_formas_e_decimal_preservados(pg, financeiro, forma):
    with pg.begin() as conn:
        p = pagar(conn, financeiro, forma=forma, valor=Decimal("0.01"))
    from app.models import PagamentoComanda
    with Session(pg) as db:
        obj = db.get(PagamentoComanda, p["id"])
        assert obj.valor == Decimal("0.01") and isinstance(obj.valor, Decimal)
        assert obj.forma == forma
        assert obj.recebido_em == p["efetiva"]
        assert obj.registrado_em.year != 2000  # trigger ignora data fornecida pelo chamador
        assert obj.registrado_em.tzinfo is not None
        assert obj.registrado_por == financeiro["user"]


@pytest.mark.parametrize("alteracoes", [{"forma": "boleto"}, {"fingerprint": "curto"},
    {"efetiva": "infinity"}, {"user": uuid4()}, {"filial": uuid4()}])
def test_forma_data_autor_contexto_e_fingerprint_invalidos(pg, financeiro, alteracoes):
    with pytest.raises(DBAPIError):
        with pg.begin() as conn:
            pagar(conn, financeiro, **alteracoes)


def test_legado_nao_recebe_sem_controle(pg, legado):
    with pytest.raises(IntegrityError):
        with pg.begin() as conn:
            pagar(conn, legado)


def test_filial_existente_divergente_e_recusada(pg, financeiro):
    with pg.begin() as conn:
        filial = uuid4()
        conn.execute(text("INSERT INTO filiais(id,empresa_id,nome) SELECT :id,empresa_id,'Ficticia' FROM filiais LIMIT 1"), {"id": filial})
    with pytest.raises(IntegrityError):
        with pg.begin() as conn:
            pagar(conn, financeiro, filial=filial)


def test_idempotencia_por_comanda_e_operacao(pg, financeiro):
    chave = uuid4()
    with pg.begin() as conn:
        p = pagar(conn, financeiro, chave=chave)
        outra = criar_comanda(conn, financeiro, dia="2099-01-02", controle=True)
        pagar(conn, outra, chave=chave)  # chave igual em outra comanda é permitida
        estornar(conn, financeiro, p["id"], chave=chave)  # operação distinta
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            pagar(conn, financeiro, chave=chave, valor=Decimal("1.00"))
    assert error.value.orig.diag.constraint_name == "uq_pagamento_idempotencia"
    with pytest.raises(IntegrityError) as error:
        with pg.begin() as conn:
            estornar(conn, financeiro, p["id"], chave=chave)
    assert error.value.orig.diag.constraint_name == "uq_estorno_idempotencia"


def test_idempotencia_concorrente_garante_um_lancamento(pg, financeiro):
    barreira = Barrier(2, timeout=10)
    chave = uuid4()
    def lancar(_):
        try:
            with pg.begin() as conn:
                conn.execute(text("SET LOCAL statement_timeout='10s'"))
                barreira.wait()
                pagar(conn, financeiro, chave=chave)
            return "ok"
        except IntegrityError as error:
            assert error.orig.diag.constraint_name == "uq_pagamento_idempotencia"
            return "duplicado"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lancar, range(2))) == ["duplicado", "ok"]
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM pagamentos_comanda")) == 1


@pytest.mark.parametrize("alteracoes", [{"valor": Decimal("0")}, {"valor": Decimal("-1")},
    {"valor": Decimal("NaN")}, {"motivo": " "}, {"comanda": uuid4()}, {"filial": uuid4()}])
def test_constraints_estorno(pg, financeiro, alteracoes):
    with pg.begin() as conn:
        p = pagar(conn, financeiro)
    with pytest.raises(DBAPIError):
        with pg.begin() as conn:
            estornar(conn, financeiro, p["id"], **alteracoes)


@pytest.mark.parametrize("total,liquido,motivo", [
    ("30.50", "30", None), ("-1", "-1", None), ("NaN", "NaN", None),
    ("0", "0", None), ("0", "0", " "),
])
def test_constraints_fechamento(pg, financeiro, total, liquido, motivo):
    with pytest.raises(DBAPIError):
        with pg.begin() as conn:
            fechar(conn, financeiro, total=Decimal(total), liquido=Decimal(liquido), motivo=motivo)


def test_fechamento_zero_com_motivo_e_sem_pagamento(pg, financeiro):
    from app.models import Comanda
    with pg.begin() as conn:
        conn.execute(text("UPDATE itens_comanda SET preco_unitario=0 WHERE comanda_id=:comanda"), financeiro)
        fechar(conn, financeiro, total=Decimal("0"), liquido=Decimal("0"), motivo="Cortesia ficticia")
    with Session(pg) as db:
        assert db.get(Comanda, financeiro["comanda"]).situacao_financeira == "fechado"
    with pg.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM pagamentos_comanda")) == 0
    with pytest.raises(IntegrityError):
        with pg.begin() as conn:
            fechar(conn, financeiro, total=Decimal("0"), liquido=Decimal("0"), motivo="Outra")


@pytest.fixture
def historico(pg, financeiro):
    with pg.begin() as conn:
        p = pagar(conn, financeiro, valor=Decimal("30.50"))
        fechar(conn, financeiro)
        estornar(conn, financeiro, p["id"])
    return financeiro


@pytest.mark.parametrize("tabela", TABELAS)
@pytest.mark.parametrize("operacao", ["UPDATE {t} SET registrado_em=now()", "DELETE FROM {t}", "TRUNCATE {t} CASCADE"])
def test_historico_imutavel_inclusive_para_owner(pg, historico, tabela, operacao):
    with pytest.raises(DBAPIError) as error:
        with pg.begin() as conn:
            conn.execute(text(operacao.format(t=tabela)))
    assert error.value.orig.pgcode == "23514"


@pytest.mark.parametrize("alvo,campo", [("comandas", "comanda"), ("usuarios", "user")])
def test_pais_nao_podem_ser_excluidos_com_historico(pg, historico, alvo, campo):
    with pytest.raises(IntegrityError):
        with pg.begin() as conn:
            conn.execute(text(f"DELETE FROM {alvo} WHERE id=:id"), {"id": historico[campo]})


def test_rls_grants_e_colunas_sem_exposicao_herdada(pg):
    with pg.connect() as conn:
        for tabela in TABELAS:
            assert conn.scalar(text("SELECT relrowsecurity FROM pg_class WHERE oid=CAST(:t AS regclass)"), {"t": "public." + tabela})
            policies = conn.execute(text("SELECT cmd,roles FROM pg_policies WHERE tablename=:t ORDER BY cmd"), {"t": tabela}).all()
            assert [(c, list(r)) for c, r in policies] == [("INSERT", ["relaxabarber_runtime"]), ("SELECT", ["relaxabarber_runtime"])]
            for role in ("anon", "authenticated", "service_role", "relaxabarber_runtime"):
                for priv in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER", "REFERENCES", "MAINTAIN"):
                    assert conn.scalar(text("SELECT has_table_privilege(:r,:t,:p)"), {"r": role, "t": "public." + tabela, "p": priv}) == (role == "relaxabarber_runtime" and priv in ("SELECT", "INSERT"))
                for priv in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
                    assert conn.scalar(text("SELECT has_any_column_privilege(:r,:t,:p)"), {"r": role, "t": "public." + tabela, "p": priv}) == (role == "relaxabarber_runtime" and priv in ("SELECT", "INSERT"))


def test_runtime_insere_sem_poder_alterar_auditoria(pg, runtime_pg, financeiro):
    with runtime_pg.begin() as conn:
        p = pagar(conn, financeiro)
        estornar(conn, financeiro, p["id"])
    # A regra ADMIN para estorno é de serviço, não inferível do login compartilhado.
    with pytest.raises(DBAPIError) as error:
        with runtime_pg.begin() as conn:
            conn.execute(text("UPDATE pagamentos_comanda SET valor=1"))
    assert error.value.orig.pgcode == "42501"
    with runtime_pg.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM pagamentos_comanda")) == 1


def test_orm_recusa_fracao_de_centavo_em_pg(pg, financeiro):
    from app.models import PagamentoComanda
    from sqlalchemy.exc import StatementError
    with Session(pg) as db:
        db.add(PagamentoComanda(comanda_id=financeiro["comanda"], filial_id=financeiro["filial"],
            valor=Decimal("1.001"), forma="pix", recebido_em=datetime.now(timezone.utc),
            registrado_por=financeiro["user"], chave_idempotencia=uuid4(), fingerprint="a" * 64))
        with pytest.raises(StatementError):
            db.flush()
        db.rollback()
