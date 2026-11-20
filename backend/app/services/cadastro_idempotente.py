from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text


def id_cadastro(recurso: str, operador: UUID, chave: UUID, filial: UUID | None = None) -> UUID:
    return uuid5(NAMESPACE_URL, f'relaxabarber:cadastro:{recurso}:{operador}:{filial}:{chave}')


def travar_cadastro(db, ident: UUID) -> None:
    if db.get_bind().dialect.name == 'postgresql':
        lock = int.from_bytes(ident.bytes[:8], 'big', signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:chave)'), {'chave': lock})
