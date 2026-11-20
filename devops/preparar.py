"""Preparo explícito do banco da disciplina, executado pelo serviço esquema."""
import getpass
import os
import subprocess
import sys

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from runtime_roles import conceder_runtime_legado


def criar_admin(engine):
    from app.core.security import hash_senha
    from app.models.empresa import Empresa
    from app.models.filial import Filial
    from app.models.usuario import PerfilEnum, Usuario
    from app.models.usuario_filial import UsuarioFilial

    email = "admin@relaxabarber.example"
    with Session(engine) as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(72418082)"))
        if db.scalar(select(Usuario.id).where(Usuario.email == email)):
            print("O administrador acadêmico já existe.")
            return
        senha = getpass.getpass("Senha local do administrador acadêmico: ")
        if not 8 <= len(senha) <= 128:
            raise SystemExit("Use uma senha de 8 a 128 caracteres.")
        filial = db.scalars(select(Filial).join(Empresa).where(Filial.ativa, Empresa.ativa)).one()
        usuario = Usuario(nome="Admin Acadêmico", email=email, perfil=PerfilEnum.ADMIN, senha_hash=hash_senha(senha))
        db.add(usuario)
        db.flush()
        db.add(UsuarioFilial(usuario_id=usuario.id, filial_id=filial.id))
    print(f"Administrador acadêmico criado: {email}")


def main():
    if sys.argv[1:] not in ([], ["admin"]):
        raise SystemExit("Argumento aceito: admin.")
    url = make_url(os.environ["DATABASE_URL"])
    if (
        (url.drivername, url.host, url.port, url.database, url.username)
        != ("postgresql+psycopg2", "banco", 5432, "relaxabarber_academico", "postgres")
        or url.query
    ):
        raise SystemExit("Destino recusado: exige o PostgreSQL acadêmico do Compose.")
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as conn:
            identidade = conn.execute(text("SELECT current_database(), current_user")).one()
            if tuple(identidade) != ("relaxabarber_academico", "postgres"):
                raise SystemExit("Identidade do PostgreSQL acadêmico não confirmada.")
        if sys.argv[1:] == ["admin"]:
            criar_admin(engine)
        else:
            subprocess.run(["alembic", "upgrade", "head"], check=True)
            conceder_runtime_legado(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
