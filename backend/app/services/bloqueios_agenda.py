from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Agendamento, BloqueioAgenda, PerfilEnum
from app.schemas.complementos_agenda import BloqueioOut, AntecedenciaAgenda
from app.services import filiais
from app.services.errors import HorarioOcupado, RecursoNaoEncontrado, SemPermissao
from app.services.permissoes_agendamento import escopo_consulta, pode_operar_profissional
from app.services.persistencia import transacao_escrita


def ativos(filial_id, barbeiro_id, data):
    return select(BloqueioAgenda).where(
        BloqueioAgenda.filial_id == filial_id,
        BloqueioAgenda.barbeiro_id == barbeiro_id,
        BloqueioAgenda.data == data,
        BloqueioAgenda.revogado_em.is_(None),
    )


def listar(db, usuario, filial_id, data):
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    profissional = escopo_consulta(usuario, None)
    consulta = select(BloqueioAgenda).where(
        BloqueioAgenda.filial_id == filial.id, BloqueioAgenda.data == data, BloqueioAgenda.revogado_em.is_(None),
    )
    if profissional is not None:
        consulta = consulta.where(BloqueioAgenda.barbeiro_id == profissional)
    return list(db.scalars(consulta.order_by(BloqueioAgenda.hora_inicio, BloqueioAgenda.id)))


def autorizar(usuario, barbeiro_id):
    if usuario.perfil == PerfilEnum.RECEPCAO or not pode_operar_profissional(usuario, barbeiro_id):
        raise SemPermissao('Somente administrador ou o próprio profissional pode gerenciar este bloqueio')


def criar(db, usuario, dados):
    from app.services.agendamento import validar_inicio

    with transacao_escrita(db):
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        autorizar(usuario, dados.barbeiro_id)
        filial = filiais.resolver_filial(db, usuario, dados.filial_id, bloquear=True)
        filiais.validar_profissional(db, dados.barbeiro_id, filial.id)
        validar_inicio(dados.data, dados.hora_inicio)
        if db.scalar(select(Agendamento.id).where(
            Agendamento.filial_id == filial.id, Agendamento.barbeiro_id == dados.barbeiro_id,
            Agendamento.data == dados.data, Agendamento.status.notin_(('cancelado', 'nao_compareceu')),
            Agendamento.hora_inicio < dados.hora_fim, Agendamento.hora_fim > dados.hora_inicio,
        ).limit(1)):
            raise HorarioOcupado('O intervalo contém agendamento')
        if db.scalar(ativos(filial.id, dados.barbeiro_id, dados.data).where(
            BloqueioAgenda.hora_inicio < dados.hora_fim, BloqueioAgenda.hora_fim > dados.hora_inicio,
        ).limit(1)):
            raise HorarioOcupado('Já existe bloqueio nesse intervalo')
        bloqueio = BloqueioAgenda(**dados.model_dump(exclude={'filial_id'}), filial_id=filial.id, criado_por=usuario.id)
        db.add(bloqueio)
        db.flush()
        return BloqueioOut.model_validate(bloqueio)


def revogar(db, usuario, filial_id, bloqueio_id):
    with transacao_escrita(db):
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        filial = filiais.resolver_filial(db, usuario, filial_id, bloquear=True)
        bloqueio = db.scalar(select(BloqueioAgenda).where(
            BloqueioAgenda.id == bloqueio_id, BloqueioAgenda.filial_id == filial.id,
            BloqueioAgenda.revogado_em.is_(None),
        ).with_for_update().execution_options(populate_existing=True))
        if bloqueio is None:
            raise RecursoNaoEncontrado('Bloqueio ativo não encontrado')
        autorizar(usuario, bloqueio.barbeiro_id)
        bloqueio.revogado_em = datetime.now(timezone.utc)
        bloqueio.revogado_por = usuario.id


def consultar_antecedencia(db, usuario, filial_id):
    filial = filiais.resolver_filial(db, usuario, filial_id)
    return AntecedenciaAgenda.model_validate(filial)


def configurar_antecedencia(db, usuario, filial_id, dados):
    from app.services.gestao_filiais import _filial_exclusiva

    with transacao_escrita(db):
        filial = _filial_exclusiva(db, usuario, filial_id)
        filial.antecedencia_reserva_horas = dados.antecedencia_reserva_horas
        filial.antecedencia_maxima_reserva_dias = dados.antecedencia_maxima_reserva_dias
        filial.antecedencia_cancelamento_horas = dados.antecedencia_cancelamento_horas
        return AntecedenciaAgenda.model_validate(filial)
