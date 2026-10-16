"""Política de cancelamento e auditoria; nenhuma conexão externa."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


def operation(routes, schemas, old='pendente', command_status='pendente', target='cancelado', reason=None):
    appointment = SimpleNamespace(filial_id=UUID('97fa517c-d7d7-4e97-a9ea-e332699918fd'), cliente_id=UUID(int=100), id=uuid4(), barbeiro_id=uuid4(), status=old)
    command = None if command_status is None else SimpleNamespace(filial_id=appointment.filial_id, cliente_id=appointment.cliente_id, barbeiro_id=appointment.barbeiro_id, status=command_status, data_abertura=None, data_fechamento=None)
    db = MagicMock()
    query = db.query.return_value
    query.populate_existing.return_value = query
    query.with_for_update.return_value = query
    query.filter.return_value = query
    query.first.side_effect = [appointment, command]
    user = SimpleNamespace(id=uuid4(), perfil='admin')
    payload = schemas.AgendamentoStatusUpdate(status=target, motivo_cancelamento=reason)
    return appointment, command, db, user, lambda: routes.atualizar_status(appointment.id, payload, db, user)


@pytest.mark.parametrize('old,status', [('pendente','pendente'), ('aguardando','aberta')])
@pytest.mark.parametrize('reason', [None, '', '  ', '  Cliente desistiu  '])
def test_cancelamento_audita_sem_fechar_comanda(routes, schemas, old, status, reason):
    appointment, command, db, user, update = operation(routes, schemas, old, status, reason=reason)
    before = datetime.now(timezone.utc)
    update()
    assert appointment.status == 'cancelado'
    assert command.status == 'cancelada'
    assert before <= appointment.cancelado_em <= datetime.now(timezone.utc)
    assert appointment.cancelado_por == user.id
    assert appointment.motivo_cancelamento == (reason.strip() or None if reason is not None else None)
    assert command.data_fechamento is None
    assert command.data_abertura is None
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    assert query_order(db) == ['Agendamento', 'Comanda']
    assert db.query.return_value.populate_existing.call_count == 2
    assert db.query.return_value.with_for_update.call_count == 2


def query_order(db):
    return [call.args[0].__name__ for call in db.query.call_args_list]


@pytest.mark.parametrize('old,status', [
    (old,status)
    for old,expected in [('pendente','pendente'),('aguardando','aberta'),('em_atendimento','aberta')]
    for status in [None,'pendente','aberta','fechada','cancelada','desconhecida']
    if status != expected
])
def test_comanda_incompativel_impede_avanco_e_cancelamento(routes, schemas, old, status):
    target = 'concluido' if old == 'em_atendimento' else 'cancelado'
    appointment, command, db, _, update = operation(routes, schemas, old, status, target)
    with pytest.raises(HTTPException) as error:
        update()
    assert error.value.status_code == 409
    assert appointment.status == old
    if command:
        assert command.status == status
    db.commit.assert_not_called()
    db.rollback.assert_called_once()


@pytest.mark.parametrize('old,code', [('em_atendimento',409), ('concluido',400), ('cancelado',400)])
def test_finais_e_inicio_impedem_cancelamento(routes, schemas, old, code):
    appointment, _, db, _, update = operation(routes, schemas, old, 'aberta')
    with pytest.raises(HTTPException) as error:
        update()
    assert error.value.status_code == code
    assert appointment.status == old
    db.commit.assert_not_called()


def test_motivo_nao_aceita_status_diferente(schemas):
    with pytest.raises(ValidationError):
        schemas.AgendamentoStatusUpdate(status='aguardando', motivo_cancelamento='motivo')


def test_estado_desconhecido_nao_vira_keyerror(routes, schemas):
    _, _, db, _, update = operation(routes, schemas, old='invalido')
    with pytest.raises(HTTPException) as error:
        update()
    assert error.value.status_code == 409
    db.rollback.assert_called_once()
