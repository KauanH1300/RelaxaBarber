from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError


def seed(db, models, schemas):
    from app.services.agendamento import criar_agendamento
    user = models.Usuario(nome='Teste', email='cancelamento@example.test', senha_hash='ficticio', perfil=models.PerfilEnum.BARBEIRO)
    client = models.Cliente(nome='Cliente', telefone='00000000000')
    service = models.Servico(nome='Corte', preco=0, tempo_estimado=30, comissao_padrao=10)
    filial = models.Filial(nome='Inicial', empresa=models.Empresa(nome='RelaxaBarber'))
    db.add_all([models.UsuarioFilial(usuario=user, filial=filial),client,service]); db.commit()
    appointment = criar_agendamento(schemas.AgendamentoCreate(cliente_id=client.id, barbeiro_id=user.id, data=date(2099,1,1), hora_inicio=time(9), servicos=[{'servico_id':service.id}]),db,user)
    command = db.scalar(select(models.Comanda).where(models.Comanda.agendamento_id == appointment.id))
    return appointment, command, user


def test_cancela_preserva_itens_valores_e_abertura(memory_session, models, schemas):
    from app.services.agendamento import atualizar_status
    db = memory_session
    appointment, command, user = seed(db,models,schemas)
    atualizar_status(appointment.id,schemas.AgendamentoStatusUpdate(status='aguardando'),db,user)
    opening = command.data_abertura
    item = command.itens[0]; service = appointment.servicos[0]
    before = (item.id,item.descricao,item.quantidade,item.preco_unitario,service.id,service.preco,service.tempo_estimado,command.valor_total)
    atualizar_status(appointment.id,schemas.AgendamentoStatusUpdate(status='cancelado', motivo_cancelamento='Desistência'),db,user)
    db.expire_all()
    assert appointment.status == 'cancelado' and command.status == 'cancelada'
    assert command.data_abertura == opening and command.data_fechamento is None
    assert before == (item.id,item.descricao,item.quantidade,item.preco_unitario,service.id,service.preco,service.tempo_estimado,command.valor_total)
    assert command.valor_total == Decimal('0.00')
    assert appointment.cancelado_por == user.id
    assert appointment.cancelado_em is not None
    assert appointment.motivo_cancelamento == 'Desistência'
    result=schemas.AgendamentoOut.model_validate(appointment)
    assert result.cancelado_por==user.id
    assert result.motivo_cancelamento=='Desistência'
    from app.schemas.comanda import ComandaResponse
    assert ComandaResponse.model_validate(command).total==command.valor_total


@pytest.mark.parametrize('phase', ['flush','commit'])
def test_falha_reverte_status_e_auditoria(memory_session, models, schemas, phase):
    from app.services.agendamento import atualizar_status
    from app.services.persistencia import FalhaPersistencia
    db=memory_session
    appointment,command,user=seed(db,models,schemas)
    ident=appointment.id
    def fail(session):
        if phase == 'commit':
            session.flush()
        raise IntegrityError('SQL-SECRETO',{},Exception('interno'))
    event_name='before_flush' if phase == 'flush' else 'before_commit'
    def flush_fail(session,context,instances):
        fail(session)
    callback=flush_fail if phase == 'flush' else fail
    event.listen(db,event_name,callback)
    try:
        with pytest.raises(FalhaPersistencia):
            atualizar_status(ident,schemas.AgendamentoStatusUpdate(status='cancelado',motivo_cancelamento='Teste'),db,user)
    finally:
        event.remove(db,event_name,callback)
    db.expire_all()
    assert appointment.status == command.status == 'pendente'
    assert appointment.cancelado_em is None and appointment.cancelado_por is None
    assert appointment.motivo_cancelamento is None and command.data_fechamento is None
    atualizar_status(ident,schemas.AgendamentoStatusUpdate(status='cancelado'),db,user)
    assert appointment.status == 'cancelado' and command.status == 'cancelada'
