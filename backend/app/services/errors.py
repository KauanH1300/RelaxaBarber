"""Erros de negócio traduzidos pela camada HTTP."""


class ErroAgendamento(Exception):
    """Base dos erros esperados do módulo."""


class AgendamentoInvalido(ErroAgendamento):
    """Solicitação incompatível com as regras atuais."""


class RecursoNaoEncontrado(ErroAgendamento):
    """Serviço ou agendamento não localizado."""


class HorarioOcupado(ErroAgendamento):
    """Profissional possui reserva sobreposta."""


class SemPermissao(ErroAgendamento):
    """Operação fora do escopo do usuário autenticado."""


class HorarioAgendamentoInvalido(AgendamentoInvalido):
    """Início incompatível com o agendamento comum."""


class ValoresAgendamentoInvalidos(AgendamentoInvalido):
    """Preço, duração ou total incompatível com o contrato de criação."""


class ClienteInativo(ErroAgendamento):
    """Cadastro existente, mas indisponível para novas reservas."""


class ConflitoEstadoAgendamento(ErroAgendamento):
    """Estado de atendimento/comanda impede a operação solicitada."""


class FilialObrigatoria(ErroAgendamento):
    """Seleção explícita necessária em contexto com várias filiais."""
