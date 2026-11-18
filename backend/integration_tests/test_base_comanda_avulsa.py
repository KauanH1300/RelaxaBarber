from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from test_concorrencia import data, insert


def test_base_avulsa_e_compatibilidade_agendada(pg, data):
    from app.models import Comanda, ItemComanda
    from app.schemas.comanda import ComandaResponse
    filial = data['filial']
    produto, avulsa, agendada = uuid4(), uuid4(), uuid4()
    with pg.begin() as db:
        agenda = insert(db, data, day='2099-04-01', status='concluido')
        db.execute(text("INSERT INTO comandas (id, filial_id, agendamento_id, cliente_id, barbeiro_id, status, valor_total) VALUES (:id,:filial,:agenda,:cliente,:profissional,'aberta',0)"), dict(id=agendada, filial=filial, agenda=agenda, cliente=data['client'], profissional=data['user']))
        db.execute(text("INSERT INTO itens_comanda (id, comanda_id, tipo, descricao, quantidade, preco_unitario) VALUES (:id,:comanda,'servico','Serviço legado',1,10)"), dict(id=uuid4(), comanda=agendada))
        db.execute(text("INSERT INTO produtos_estoque (id, filial_id, nome, unidade, venda, consumo, custo, preco_venda, estoque_minimo) VALUES (:id,:filial,'Produto','un',true,false,2,5,0)"), dict(id=produto, filial=filial))
        db.execute(text("INSERT INTO comandas (id, filial_id, tipo, status, valor_total) VALUES (:id,:filial,'avulsa','aberta',0)"), dict(id=avulsa, filial=filial))
        db.execute(text("INSERT INTO itens_comanda (id,comanda_id,comanda_tipo,filial_id,produto_id,tipo,descricao,quantidade,preco_unitario,custo_snapshot,comissao_percentual_snapshot) VALUES (:id,:comanda,'avulsa',:filial,:produto,'produto','Produto',2,5,2,10)"), dict(id=uuid4(), comanda=avulsa, filial=filial, produto=produto))
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text("INSERT INTO itens_comanda (id,comanda_id,comanda_tipo,tipo,descricao,quantidade,preco_unitario) VALUES (:id,:comanda,'avulsa','servico','Inválido',1,5)"), dict(id=uuid4(), comanda=avulsa))
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text("INSERT INTO itens_comanda (id,comanda_id,tipo,descricao,quantidade,preco_unitario) VALUES (:id,:comanda,'servico','Inválido',1,5)"), dict(id=uuid4(), comanda=avulsa))
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text("INSERT INTO comandas (id,filial_id,tipo,status,valor_total) VALUES (:id,:filial,'agendada','aberta',0)"), dict(id=uuid4(), filial=filial))
        outra_filial, outro_produto = uuid4(), uuid4()
        db.execute(text("INSERT INTO filiais (id,empresa_id,nome) SELECT :id,empresa_id,'Outra' FROM filiais WHERE id=:filial"), dict(id=outra_filial, filial=filial))
        db.execute(text("INSERT INTO produtos_estoque (id,filial_id,nome,unidade,venda,consumo,custo,preco_venda,estoque_minimo) VALUES (:id,:filial,'Outro','un',true,false,2,5,0)"), dict(id=outro_produto, filial=outra_filial))
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(text("INSERT INTO itens_comanda (id,comanda_id,comanda_tipo,filial_id,produto_id,tipo,descricao,quantidade,preco_unitario,custo_snapshot,comissao_percentual_snapshot) VALUES (:id,:comanda,'avulsa',:filial,:produto,'produto','Inválido',1,5,2,10)"), dict(id=uuid4(), comanda=avulsa, filial=filial, produto=outro_produto))
    with Session(pg) as db:
        anterior = ComandaResponse.model_validate(db.get(Comanda, agendada))
        nova = ComandaResponse.model_validate(db.get(Comanda, avulsa))
        assert anterior.tipo == 'agendada' and anterior.agendamento_id == agenda
        assert anterior.itens[0].tipo == 'servico' and anterior.total == 10
        assert nova.tipo == 'avulsa' and nova.agendamento_id is None and nova.cliente_id is None and nova.barbeiro_id is None
        assert nova.itens[0].produto_id == produto and nova.total == 10
        assert db.get(ItemComanda, nova.itens[0].id).custo_snapshot == 2
        from app.models import Usuario, PerfilEnum
        from app.services.comandas import buscar_detalhe
        admin = Usuario(nome='Admin QA', email='admin.avulsa@example.test', senha_hash='ficticio', perfil=PerfilEnum.ADMIN)
        db.add(admin); db.commit()
        detalhe = buscar_detalhe(db, admin, avulsa, filial)
        assert detalhe.tipo == 'avulsa' and detalhe.cliente is None and detalhe.profissional is None and detalhe.atendimento is None
        assert buscar_detalhe(db, admin, agendada, filial).atendimento.id == agenda
