"""Consultas de cadastro e vínculo idempotente, sem confirmar transações."""
import re
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import aliased

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


def filtrar_busca(query, busca, *, normalizar_telefone=False):
    if busca:
        valor = busca.strip()
        telefone = telefone_para_busca(valor) if normalizar_telefone else None
        if telefone:
            query = query.filter(Cliente.telefone_normalizado == telefone)
        else:
            termo = f'%{valor}%'
            query = query.filter(or_(Cliente.nome.ilike(termo), Cliente.telefone.ilike(termo)))
    return query.order_by(Cliente.nome, Cliente.id)


def telefone_para_busca(valor):
    # Mesma regra da coluna gerada por normalizar_telefone_cliente no PostgreSQL.
    if not re.fullmatch(r'[0-9+().\s-]+', valor):
        return None
    digitos = re.sub(r'[^0-9]', '', valor)
    if re.fullmatch(r'[1-9][0-9]{9,10}', digitos):
        return '55' + digitos
    if re.fullmatch(r'[1-9][0-9]{11,14}', digitos) and not digitos.startswith('550'):
        return digitos
    return None


def possivel_duplicidade(filial_id):
    outro = aliased(Cliente)
    vinculo = aliased(ClienteFilial)
    return select(outro.id).join(vinculo, vinculo.cliente_id == outro.id).where(
        vinculo.filial_id == filial_id,
        outro.id != Cliente.id, outro.ativo.is_(True),
        outro.telefone_normalizado == Cliente.telefone_normalizado,
    ).correlate(Cliente).exists()


def consulta_local(db, filial_id):
    return db.query(Cliente).join(ClienteFilial, ClienteFilial.cliente_id == Cliente.id).filter(
        ClienteFilial.filial_id == filial_id,
    )
