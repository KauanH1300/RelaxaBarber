"""Atomicidade real do ORM em SQLite em memória; não substitui PostgreSQL."""
from datetime import date, time
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select, func
from sqlalchemy.exc import IntegrityError


def setup_data(db, models):
    user = models.Usuario(nome='Teste', email='teste@example.com', senha_hash='ficticio', perfil=models.PerfilEnum.ADMIN)
    client = models.Cliente(nome='Cliente teste', telefone='81999999999')
    service = models.Servico(nome='Corte', preco=Decimal('30.00'), tempo_estimado=30, comissao_padrao=10)
    db.add_all([user, client, service])
    db.commit()
    return user, client, service


def data_create(schemas, client, user, service):
    return schemas.AgendamentoCreate(cliente_id=client.id, barbeiro_id=user.id,
        data=date(2099, 1, 1), hora_inicio=time(9), servicos=[{'servico_id':service.id}])


@pytest.mark.parametrize('table', ['agendamentos', 'agendamento_servicos', 'comandas', 'itens_comanda'])
def test_criacao_inteira_revertida(memory_session, models, schemas, table, isolated_runtime):
    from app.services.agendamento import criar_agendamento
    from app.services.persistencia import FalhaPersistencia
    db = memory_session
    user, client, service = setup_data(db, models)
    # Profissional ativo; ADMIN solicita para um barbeiro da mesma entidade.
    user.perfil = models.PerfilEnum.BARBEIRO
    db.commit()
    data = data_create(schemas, client, user, service)
    engine = db.get_bind()
    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO ' + table + ' '):
            raise IntegrityError('SQL interno', parameters, Exception('Falha simulada'))
    event.listen(engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(FalhaPersistencia):
            criar_agendamento(data, db, user)
    finally:
        event.remove(engine, 'before_cursor_execute', fail)
    for model in [models.Agendamento, models.AgendamentoServico, models.Comanda, models.ItemComanda]:
        assert db.scalar(select(func.count()).select_from(model)) == 0
    # A mesma sessão está operacional após rollback e admite criação completa.
    criar_agendamento(data, db, user)
    for model in [models.Agendamento, models.AgendamentoServico, models.Comanda, models.ItemComanda]:
        assert db.scalar(select(func.count()).select_from(model)) == 1


def test_status_e_comanda_revertidos_juntos(memory_session, models, schemas, isolated_runtime):
    from app.services.agendamento import criar_agendamento, atualizar_status
    from app.services.persistencia import FalhaPersistencia
    db = memory_session
    user, client, service = setup_data(db, models)
    professional = models.Usuario(nome='Barbeiro', email='barbeiro@example.com', senha_hash='ficticio', perfil=models.PerfilEnum.BARBEIRO)
    db.add(professional); db.commit()
    appointment = criar_agendamento(data_create(schemas, client, professional, service), db, user)
    appointment_id = appointment.id
    def fail(session):
        session.flush()  # alterações efetivamente enviadas antes da falha do commit
        raise IntegrityError('SQL interno', {}, Exception('Falha simulada'))
    event.listen(db, 'before_commit', fail)
    try:
        with pytest.raises(FalhaPersistencia):
            atualizar_status(appointment_id, schemas.AgendamentoStatusUpdate(status='aguardando'), db, user)
    finally:
        event.remove(db, 'before_commit', fail)
    assert db.get(models.Agendamento, appointment_id).status == 'pendente'
    command = db.scalar(select(models.Comanda).where(models.Comanda.agendamento_id == appointment_id))
    assert command.status == 'pendente'
    assert command.data_abertura is None
    atualizar_status(appointment_id, schemas.AgendamentoStatusUpdate(status='aguardando'), db, user)
    assert command.status == 'aberta'


def test_violacao_fk_real_nao_deixa_sessao_inutilizavel(memory_session, models, isolated_runtime):
    from uuid import uuid4
    from app.services.persistencia import transacao_escrita, FalhaPersistencia
    db = memory_session
    with pytest.raises(FalhaPersistencia):
        with transacao_escrita(db):
            db.add(models.ItemComanda(comanda_id=uuid4(), tipo='servico', descricao='Teste', quantidade=1, preco_unitario=1))
            db.flush()
    assert db.scalar(select(func.count()).select_from(models.ItemComanda)) == 0


def test_refresh_falha_mas_commit_ja_persistiu_todo_conjunto(memory_session, models, schemas, isolated_runtime):
    from sqlalchemy.exc import OperationalError
    from app.services.agendamento import criar_agendamento
    from app.services.persistencia import FalhaLeituraAposCommit
    db = memory_session
    user, client, service = setup_data(db, models)
    professional = models.Usuario(nome='Barbeiro', email='outro@example.com', senha_hash='ficticio', perfil=models.PerfilEnum.BARBEIRO)
    db.add(professional); db.commit()
    data = data_create(schemas, client, professional, service)
    confirmed = False
    def after_commit(session):
        nonlocal confirmed
        confirmed = True
    def fail_refresh(connection, cursor, statement, parameters, context, executemany):
        if confirmed and 'FROM agendamentos' in statement:
            raise OperationalError('SQL interno', {}, Exception('Falha de leitura'))
    event.listen(db, 'after_commit', after_commit)
    event.listen(db.get_bind(), 'before_cursor_execute', fail_refresh)
    try:
        with pytest.raises(FalhaLeituraAposCommit):
            criar_agendamento(data, db, user)
    finally:
        event.remove(db, 'after_commit', after_commit)
        event.remove(db.get_bind(), 'before_cursor_execute', fail_refresh)
    assert confirmed
    for model in [models.Agendamento, models.AgendamentoServico, models.Comanda, models.ItemComanda]:
        assert db.scalar(select(func.count()).select_from(model)) == 1
