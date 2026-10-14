"""Erros de negócio traduzidos pela camada HTTP."""


class ErroAgendamento(Exception):
    """Base dos erros esperados do módulo."""


class AgendamentoInvalido(ErroAgendamento):
    """Solicitação incompatível com as regras atuais."""


class RecursoNaoEncontrado(ErroAgendamento):
    """Serviço ou agendamento não localizado."""


class HorarioOcupado(ErroAgendamento):
    """Profissional possui reserva sobreposta."""
