"""Erros de domínio financeiro, independentes de HTTP e das mensagens do driver."""


class ErroFinanceiro(Exception):
    pass


class EntradaFinanceiraInvalida(ErroFinanceiro):
    pass


class AcessoFinanceiroNegado(ErroFinanceiro):
    pass


class ComandaFinanceiraNaoEncontrada(ErroFinanceiro):
    pass


class HistoricoFinanceiroNaoVerificado(ErroFinanceiro):
    pass


class EstadoFinanceiroIncompativel(ErroFinanceiro):
    pass


class SaldoInsuficiente(ErroFinanceiro):
    pass


class LimiteEstornoExcedido(ErroFinanceiro):
    pass


class ConflitoIdempotenciaFinanceira(ErroFinanceiro):
    pass


class DadosFinanceirosInconsistentes(ErroFinanceiro):
    pass
