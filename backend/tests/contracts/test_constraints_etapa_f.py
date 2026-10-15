"""DDL de PostgreSQL e compatibilidade com SQLite, sem conexão externa."""
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql, sqlite


def test_constraints_correspondem_ao_contrato(models):
    table = models.Agendamento.__table__
    pg = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert 'EXCLUDE USING gist' in pg
    assert "tsrange(data + hora_inicio, data + hora_fim, '[)') WITH &&" in pg
    assert "status <> 'cancelado'" in pg
    assert 'NOT DEFERRABLE' in pg
    assert 'CHECK (hora_fim > hora_inicio)' in pg
    local = str(CreateTable(table).compile(dialect=sqlite.dialect()))
    assert 'EXCLUDE' not in local
    assert 'CHECK (hora_fim > hora_inicio)' in local
