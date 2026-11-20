"""Reagendamento na mesma reserva/comanda; locks na ordem filial, reserva, comanda."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.models import Agendamento, Comanda, Reagendamento
from app.schemas.agendamento import AgendamentoOut
from app.schemas.reagendamento import ReagendamentoOut
from app.services import filiais, agendamento as agenda
from app.services.errors import RecursoNaoEncontrado, SemPermissao, ConflitoEstadoAgendamento
from app.services.permissoes_agendamento import pode_operar_profissional
from app.services.persistencia import transacao_escrita


def _versao(value):
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def reagendar(agendamento_id, dados, db, usuario, filial_id=None):
    with transacao_escrita(db), db.no_autoflush:
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        try:
            unidade = filiais.filial_do_registro(db, usuario, Agendamento, agendamento_id, escrita=True)
            if filial_id is not None and filial_id != unidade:
                raise RecursoNaoEncontrado('Agendamento não encontrado')
            filiais.resolver_filial(db, usuario, unidade, bloquear=True)
        except (SemPermissao, RecursoNaoEncontrado):
            raise RecursoNaoEncontrado('Agendamento não encontrado') from None
        reserva = db.scalar(select(Agendamento).where(
            Agendamento.id == agendamento_id, Agendamento.filial_id == unidade,
        ).with_for_update().execution_options(populate_existing=True))
        if reserva is None or not pode_operar_profissional(usuario, reserva.barbeiro_id):
            raise RecursoNaoEncontrado('Agendamento não encontrado')
        if not pode_operar_profissional(usuario, dados.barbeiro_id):
            raise SemPermissao('Sem permissão para transferir atendimento para outro profissional')
        resultado = aplicar_reagendamento(db, reserva, dados, registrado_por=usuario.id)
    return resultado


def aplicar_reagendamento(db, reserva, dados, registrado_por=None, registrado_por_cliente=None):
    if reserva.status not in ('pendente', 'aguardando'):
        raise ConflitoEstadoAgendamento('Somente atendimentos pendentes ou aguardando podem ser reagendados')
    if _versao(reserva.atualizado_em) != _versao(dados.atualizado_em_esperado):
        raise ConflitoEstadoAgendamento('Agendamento alterado por outra operação. Atualize antes de reagendar')
    if datetime.combine(reserva.data, reserva.hora_fim, tzinfo=agenda.FUSO_BARBEARIA) <= agenda.agora_local():
        raise ConflitoEstadoAgendamento('Atendimento vencido não pode ser reagendado')
    comanda = db.scalar(select(Comanda).where(Comanda.agendamento_id == reserva.id)
                        .with_for_update().execution_options(populate_existing=True))
    if (comanda is None or (comanda.filial_id, comanda.cliente_id, comanda.barbeiro_id) !=
            (reserva.filial_id, reserva.cliente_id, reserva.barbeiro_id)):
        raise ConflitoEstadoAgendamento('Comanda incompatível com o agendamento')
    if comanda.status != {'pendente': 'pendente', 'aguardando': 'aberta'}[reserva.status]:
        raise ConflitoEstadoAgendamento('Estado da comanda incompatível com o reagendamento')
    db.expire(comanda, ['controle_financeiro'])
    if comanda.controle_financeiro is not None and comanda.controle_financeiro.fechamento is not None:
        raise ConflitoEstadoAgendamento('Comanda encerrada financeiramente não permite reagendamento')
    if registrado_por_cliente is not None and dados.duracao_min is not None:
        raise SemPermissao('Clientes não podem alterar a duração')
    filial = reserva.filial
    agenda.validar_inicio(dados.data, dados.hora_inicio)
    filiais.validar_profissional(db, dados.barbeiro_id, reserva.filial_id)
    hora_fim = agenda.calcular_termino(dados.data, dados.hora_inicio,
                                     dados.duracao_min or agenda.duracao_reservada(reserva))
    if (reserva.data, reserva.hora_inicio, reserva.hora_fim, reserva.barbeiro_id) == (
        dados.data, dados.hora_inicio, hora_fim, dados.barbeiro_id
    ):
        raise ConflitoEstadoAgendamento('Informe uma nova data, horário, duração ou barbeiro')
    agenda.validar_disponibilidade(db, reserva.filial_id, dados.barbeiro_id, dados.data,
                                  dados.hora_inicio, hora_fim, ignorar_id=reserva.id)
    db.add(Reagendamento(agendamento_id=reserva.id, registrado_por=registrado_por, registrado_por_cliente=registrado_por_cliente, motivo=dados.motivo,
        data_anterior=reserva.data, hora_inicio_anterior=reserva.hora_inicio,
        hora_fim_anterior=reserva.hora_fim, barbeiro_id_anterior=reserva.barbeiro_id,
        data_nova=dados.data, hora_inicio_nova=dados.hora_inicio,
        hora_fim_nova=hora_fim, barbeiro_id_novo=dados.barbeiro_id))
    profissional_anterior = reserva.barbeiro_id
    reserva.data, reserva.hora_inicio, reserva.hora_fim = dados.data, dados.hora_inicio, hora_fim
    reserva.barbeiro_id = dados.barbeiro_id
    reserva.atualizado_em = datetime.now(timezone.utc)
    db.flush()  # A FK CASCADE mantém a mesma comanda e seus vínculos financeiros.
    db.expire(comanda, ['barbeiro_id'])
    if profissional_anterior != dados.barbeiro_id and comanda.comissoes_ativas:
        from app.models import ItemComanda
        from app.services import comissoes
        from decimal import Decimal
        for item in db.scalars(select(ItemComanda).where(ItemComanda.comanda_id == comanda.id, ItemComanda.ativo.is_(True))):
            comissoes.fixar(db, comanda, item, dados.barbeiro_id)
        comissoes.registrar(db, comanda, Decimal('0.00'), 'transferencia', registrado_por)
    db.expire(reserva, ['barbeiro'])
    resultado = AgendamentoOut.model_validate(reserva)
    return resultado


def historico(agendamento_id, db, usuario, filial_id=None):
    agenda.buscar_agendamento(agendamento_id, db, usuario, filial_id)
    return [ReagendamentoOut.model_validate(r) for r in db.scalars(select(Reagendamento).where(
        Reagendamento.agendamento_id == agendamento_id,
    ).order_by(Reagendamento.registrado_em, Reagendamento.id))]
