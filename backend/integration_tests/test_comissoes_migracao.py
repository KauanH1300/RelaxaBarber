"""Compatibilidade da migração com dados fictícios anteriores em banco descartável."""
from uuid import uuid4
from decimal import Decimal
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from pathlib import Path

@pytest.mark.parametrize('percentual', [Decimal('10'),Decimal('125')])
def test_migracao_preserva_dados_ou_recusa_percentual_invalido(pg_engine, percentual):
    config=Config();config.set_main_option('script_location',str(Path(__file__).resolve().parents[1]/'alembic'))
    scripts=ScriptDirectory.from_config(config)
    ids={'usuario':uuid4(),'cliente':uuid4(),'servico':uuid4(),'agenda':uuid4(),'comanda':uuid4(),'item':uuid4(),'produto':uuid4(),'percentual':percentual}
    with pg_engine.begin() as c:
        c.execute(text('DROP SCHEMA public CASCADE'));c.execute(text('CREATE SCHEMA public AUTHORIZATION rb_horarios_migrador'));c.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
        c.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC, anon, authenticated, service_role, relaxabarber_runtime'))
        for rev in reversed(list(scripts.walk_revisions(base='base',head='e70c15a9f321'))):
            with Operations.context(MigrationContext.configure(c)): rev.module.upgrade()
        ids['filial']=c.scalar(text('SELECT id FROM filiais LIMIT 1'))
        c.execute(text("INSERT INTO usuarios(id,nome,email,senha_hash,perfil,ativo) VALUES(:usuario,'Fictício','comissao@example.test','ficticio','BARBEIRO',true)"),ids)
        c.execute(text("INSERT INTO usuario_filiais(id,usuario_id,filial_id,ativo) VALUES(:id,:usuario,:filial,true)"),ids|{'id':uuid4()})
        c.execute(text("INSERT INTO clientes(id,nome,telefone,conta_ativada,saldo,ativo) VALUES(:cliente,'Fictício','00001',false,0,true)"),ids)
        c.execute(text("INSERT INTO servicos(id,nome,preco,tempo_estimado,comissao_padrao,ativo) VALUES(:servico,'Serviço',30,30,:percentual,true)"),ids)
        c.execute(text("INSERT INTO agendamentos(id,filial_id,cliente_id,barbeiro_id,data,hora_inicio,hora_fim,status,origem) VALUES(:agenda,:filial,:cliente,:usuario,'2099-01-01','09:00','09:30','pendente','recepcao')"),ids)
        c.execute(text("INSERT INTO comandas(id,filial_id,agendamento_id,cliente_id,barbeiro_id,valor_total,status) VALUES(:comanda,:filial,:agenda,:cliente,:usuario,30,'pendente')"),ids)
        c.execute(text("INSERT INTO itens_comanda(id,comanda_id,tipo,servico_id,descricao,quantidade,preco_unitario) VALUES(:item,:comanda,'servico',:servico,'Histórico',1,30)"),ids)
        c.execute(text("INSERT INTO produtos_estoque(id,filial_id,nome,unidade,venda,consumo,custo,preco_venda,estoque_minimo) VALUES(:produto,:filial,'Produto','un',true,false,2,3,0)"),ids)
        antes=c.execute(text('SELECT valor_total,status FROM comandas WHERE id=:comanda'),ids).one()
    def migrar():
        with pg_engine.begin() as c:
            c.execute(text('SET LOCAL ROLE rb_horarios_migrador'))
            with Operations.context(MigrationContext.configure(c)): scripts.get_revision('e12a46c8179b').module.upgrade()
    if percentual>100:
        with pytest.raises(DBAPIError): migrar()
        with pg_engine.connect() as c:
            assert c.scalar(text('SELECT comissao_padrao FROM servicos WHERE id=:servico'),ids)==percentual
            assert c.scalar(text("SELECT to_regclass('public.eventos_comissao')")) is None
            assert c.execute(text('SELECT valor_total,status FROM comandas WHERE id=:comanda'),ids).one()==antes
    else:
        migrar()
        with pg_engine.connect() as c:
            assert c.execute(text('SELECT valor_total,status FROM comandas WHERE id=:comanda'),ids).one()==antes
            assert c.scalar(text('SELECT comissoes_ativas FROM comandas WHERE id=:comanda'),ids) is False
            assert c.scalar(text('SELECT comissao_padrao FROM produtos_estoque WHERE id=:produto'),ids)==0
            assert c.scalar(text('SELECT count(*) FROM eventos_comissao'))==0
