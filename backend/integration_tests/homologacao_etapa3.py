"""Provisionamento opt-in EXCLUSIVO do namespace Docker sem rede da homologação.

Não importa configurações locais e recusa qualquer destino diferente do fixture.
Executar somente após comprovar --network none no container PostgreSQL.
"""
import json
import os
from pathlib import Path
import socket
from uuid import uuid4

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session


def main():
    assert os.environ.get('RB_HOMOLOG_ISOLADO') == 'descartavel-sem-rede'
    assert not Path('/source/.env').exists()
    assert not Path('/app/.env').exists()
    url = 'postgresql+psycopg2://rb_concorrencia_test@127.0.0.1:55432/relaxabarber_concorrencia_test'
    assert os.environ['DATABASE_URL'] == url
    with socket.socket() as probe:
        probe.settimeout(1)
        assert probe.connect_ex(('1.1.1.1', 443)) != 0
    engine = create_engine(url)
    with engine.connect() as conn:
        identity = conn.execute(text('SELECT current_database(),current_user,inet_server_addr()::text,inet_server_port()')).one()
        assert tuple(identity) == ('relaxabarber_concorrencia_test', 'rb_concorrencia_test', '127.0.0.1/32', 55432)
    from runtime_roles import provisionar_papeis, conceder_runtime_legado
    provisionar_papeis(engine)
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    config = Config()
    config.set_main_option('script_location', '/source/alembic')
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA public CASCADE'))
        conn.execute(text('CREATE SCHEMA public AUTHORIZATION rb_horarios_migrador'))
        conn.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        for revision in reversed(list(ScriptDirectory.from_config(config).walk_revisions())):
            with Operations.context(MigrationContext.configure(conn)):
                revision.module.upgrade()
    conceder_runtime_legado(engine)
    from app.models import Usuario, PerfilEnum, UsuarioFilial, Filial, Cliente, Servico
    from app.core.security import hash_senha
    seed = {'usuarios': {}}
    with Session(engine) as db:
        filial = db.scalar(select(Filial))
        outra = Filial(nome='Homologacao isolada B', empresa_id=filial.empresa_id)
        db.add(outra)
        client = Cliente(nome='Cliente homologacao descartavel', telefone='00000000000')
        service = Servico(nome='Servico homologacao 300', preco=300, tempo_estimado=30, comissao_padrao=0)
        db.add_all([client, service])
        for perfil in PerfilEnum:
            u = Usuario(nome=f'Homologacao {perfil.value}', email=f'{perfil.value}@homolog.example.com',
                        senha_hash=hash_senha('Somente-local-123!'), perfil=perfil)
            db.add(u)
            db.flush()
            db.add(UsuarioFilial(usuario_id=u.id, filial_id=filial.id))
            seed['usuarios'][perfil.value] = str(u.id)
        db.flush()
        seed.update(filial=str(filial.id), outra_filial=str(outra.id), cliente=str(client.id), servico=str(service.id))
        db.commit()
    # Fixtures históricas explícitas, jamais criadas por um endpoint de parcial.
    with engine.begin() as conn:
        for name, day in [('quitada', '2099-01-01'), ('legado', '2099-01-02')]:
            params = dict(a=uuid4(), c=uuid4(), f=seed['filial'], u=seed['usuarios']['barbeiro'], client=seed['cliente'], day=day)
            conn.execute(text("INSERT INTO agendamentos(id,filial_id,cliente_id,barbeiro_id,data,hora_inicio,hora_fim,status,origem) VALUES(:a,:f,:client,:u,:day,'09:00','09:30','concluido','recepcao')"), params)
            conn.execute(text("INSERT INTO comandas(id,filial_id,agendamento_id,cliente_id,barbeiro_id,status,valor_total,data_fechamento) VALUES(:c,:f,:a,:client,:u,'fechada',30.50,now())"), params)
            conn.execute(text("INSERT INTO itens_comanda(id,comanda_id,tipo,descricao,quantidade,preco_unitario) VALUES(:id,:c,'servico','Fixture historica',1,30.50)"), params | {'id': uuid4()})
            if name == 'quitada':
                conn.execute(text("INSERT INTO controles_financeiros_comanda(comanda_id,filial_id,registrado_por,motivo) VALUES(:c,:f,:u,'Fixture historica verificada')"), params)
                conn.execute(text("INSERT INTO pagamentos_comanda(id,comanda_id,filial_id,valor,forma,recebido_em,registrado_por,chave_idempotencia,fingerprint) VALUES(:id,:c,:f,30.50,'pix',now(),:u,:key,:fp)"), params | {'id': uuid4(), 'key': uuid4(), 'fp': 'a' * 64})
            seed[name] = str(params['c'])
    Path('/tmp/homolog-seed.json').write_text(json.dumps(seed))
    print('ISOLAMENTO E PROVISIONAMENTO APROVADOS', json.dumps(seed))


if __name__ == '__main__':
    main()
