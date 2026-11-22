"""Sugestões de agenda interna. A gravação revalida a escolha normalmente."""
from sqlalchemy import select

from app.models import Servico
from app.services import agendamento, filiais, jornada, otimizacao_agenda, reserva_publica
from app.services.errors import ConflitoEstadoAgendamento, RecursoNaoEncontrado, ValoresAgendamentoInvalidos
from app.services.permissoes_agendamento import pode_operar_profissional


def consultar(db, usuario, filial_id, data, servicos_ids, duracao, agendamento_id):
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    reserva = None
    if agendamento_id is not None:
        reserva = agendamento.buscar_agendamento(agendamento_id, db, usuario, filial.id)
        if not pode_operar_profissional(usuario, reserva.barbeiro_id):
            raise RecursoNaoEncontrado('Agendamento não encontrado')
        if reserva.status not in ('pendente', 'aguardando'):
            raise ConflitoEstadoAgendamento('Este atendimento não pode ser reagendado.')
        servicos_ids = [item.servico_id for item in reserva.servicos]
        duracao = duracao or agendamento.duracao_reservada(reserva)
    elif servicos_ids:
        servicos = list(db.scalars(select(Servico).where(Servico.id.in_(servicos_ids), Servico.ativo.is_(True))))
        if {s.id for s in servicos} != set(servicos_ids):
            raise RecursoNaoEncontrado('Serviço indisponível')
        duracao = duracao or sum(s.tempo_estimado for s in servicos)
    if not servicos_ids or duracao is None or not 1 <= duracao <= 480:
        raise ValoresAgendamentoInvalidos('Selecione os serviços e informe uma duração entre 1 e 480 minutos.')

    equipe = [p for p in reserva_publica.profissionais(db, filial.id, servicos_ids)
              if pode_operar_profissional(usuario, p.id)]
    candidatos = jornada.candidatos_da_agenda(db, filial.id, equipe, data, duracao, agendamento_id)
    nomes = {str(p.id): p.nome for p in equipe}
    if reserva and data == reserva.data and duracao == agendamento.duracao_reservada(reserva):
        candidatos = [c for c in candidatos if not (
            c.profissional == str(reserva.barbeiro_id)
            and reserva.hora_inicio.isoformat() == reserva_publica.formatar_horario(c.inicio) + ':00'
        )]
    classificados = sorted(zip(otimizacao_agenda.avaliar(candidatos), candidatos), key=lambda par: par[0])
    return [
        {'hora_inicio': reserva_publica.formatar_horario(c.inicio),
         'barbeiro_id': c.profissional, 'barbeiro': nomes[c.profissional]}
        for _, c in classificados[:5]
    ]
