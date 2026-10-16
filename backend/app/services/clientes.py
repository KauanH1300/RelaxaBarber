"""Consultas de cadastro e vínculo idempotente, sem confirmar transações."""
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models import Cliente, ClienteFilial


def garantir_vinculo(db, cliente_id, filial_id):
    """Participa da transação do chamador; apenas o conflito do par é ignorado.

    Não capturar IntegrityError: FKs e demais falhas precisam abortar o conjunto.
    PostgreSQL arbitra duas primeiras associações concorrentes pela UNIQUE.
    SQLite existe exclusivamente para os testes isolados em memória.
    """
    dialect = db.get_bind().dialect.name
    if dialect == 'postgresql':
        insert = pg_insert
    elif dialect == 'sqlite':
        insert = sqlite_insert
    else:
        raise RuntimeError('Banco sem suporte ao vínculo idempotente de clientes')
    statement = insert(ClienteFilial).values(
        id=uuid4(), cliente_id=cliente_id, filial_id=filial_id,
    ).on_conflict_do_nothing(index_elements=['cliente_id', 'filial_id'])
    db.execute(statement)


def filtrar_busca(query, busca):
    if busca:
        termo = f'%{busca.strip()}%'
        query = query.filter(or_(Cliente.nome.ilike(termo), Cliente.telefone.ilike(termo)))
    return query.order_by(Cliente.nome, Cliente.id)


def consulta_local(db, filial_id):
    return db.query(Cliente).join(ClienteFilial, ClienteFilial.cliente_id == Cliente.id).filter(
        ClienteFilial.filial_id == filial_id,
    )
