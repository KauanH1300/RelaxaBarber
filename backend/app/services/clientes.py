"""Consultas de cadastro e vínculo idempotente, sem confirmar transações."""
import re
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import aliased

from app.models import Cliente, ClienteFilial, ContaPortalCliente
from app.schemas.cliente import ClienteDuplicidadeOut, GrupoDuplicidadeOut


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


def coincidencias_por_telefone(db, filial_id, telefone, ignorar_id=None):
    normalizado = telefone_para_busca(telefone.strip())
    if not normalizado:
        return []
    query = consulta_local(db, filial_id).filter(
        Cliente.ativo.is_(True), Cliente.telefone_normalizado == normalizado,
    )
    if ignorar_id is not None:
        query = query.filter(Cliente.id != ignorar_id)
    return query.order_by(Cliente.nome, Cliente.id).limit(20).all()


def grupos_duplicidade(db, filial_id):
    locais = consulta_local(db, filial_id).outerjoin(
        ContaPortalCliente, ContaPortalCliente.cliente_id == Cliente.id,
    ).filter(
        Cliente.ativo.is_(True), Cliente.telefone_normalizado.is_not(None),
    )
    tem_conta = Cliente.conta_ativada.is_(True) & ContaPortalCliente.cliente_id.is_not(None)
    online = func.count().filter(tem_conta)
    presencial = func.count().filter(~tem_conta)
    misto = ((online > 0) & (presencial > 0)).label('misto')
    grupos = locais.with_entities(Cliente.telefone_normalizado, misto).group_by(
        Cliente.telefone_normalizado,
    ).having(func.count() > 1).subquery()
    linhas = locais.join(grupos, grupos.c.telefone_normalizado == Cliente.telefone_normalizado).add_columns(
        grupos.c.misto, tem_conta,
    ).order_by(grupos.c.misto.desc(), Cliente.telefone_normalizado, tem_conta,
               Cliente.nome, Cliente.id)
    resultado = {}
    for cliente, inclui_ambos, conta_verificada in linhas:
        telefone = cliente.telefone_normalizado
        if telefone not in resultado:
            resultado[telefone] = GrupoDuplicidadeOut(
                telefone_normalizado=telefone, inclui_presencial_e_online=inclui_ambos, clientes=[],
            )
        registro = ClienteDuplicidadeOut(id=cliente.id, nome=cliente.nome, telefone=cliente.telefone,
                                         conta_ativada=conta_verificada)
        resultado[telefone].clientes.append(registro)
    return list(resultado.values())
