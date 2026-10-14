import pytest


def test_engine_real_proibida(isolated_runtime):
    import sqlalchemy

    with pytest.raises(AssertionError, match="acesso ao banco"):
        sqlalchemy.create_engine("postgresql://nao-deve-conectar")


def test_dependencia_real_de_banco_proibida(isolated_runtime):
    from app.db.database import get_db

    with pytest.raises(AssertionError, match="acesso ao banco"):
        get_db()
