"""Tradução HTTP restrita às rotas financeiras; nunca transporta texto do driver."""
import logging

from fastapi import HTTPException
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError, OperationalError, DisconnectionError, TimeoutError

from app.services import financeiro_errors as dominio
from app.services import persistencia as p

logger = logging.getLogger(__name__)

ERROS = {
    dominio.EntradaFinanceiraInvalida: (422, 'entrada_financeira_invalida', 'Dados financeiros inválidos'),
    dominio.AcessoFinanceiroNegado: (403, 'acesso_financeiro_negado', 'Sem permissão financeira ativa'),
    dominio.ComandaFinanceiraNaoEncontrada: (404, 'comanda_financeira_nao_encontrada', 'Comanda não encontrada'),
    dominio.HistoricoFinanceiroNaoVerificado: (409, 'historico_financeiro_nao_verificado', 'Conciliação financeira específica necessária'),
    dominio.EstadoFinanceiroIncompativel: (409, 'estado_financeiro_incompativel', 'Estado incompatível com a operação financeira'),
    dominio.SaldoInsuficiente: (409, 'saldo_insuficiente', 'Saldo incompatível com o pagamento ou fechamento'),
    dominio.LimiteEstornoExcedido: (409, 'limite_estorno_excedido', 'Estorno superior ao disponível no pagamento'),
    dominio.ConflitoIdempotenciaFinanceira: (409, 'conflito_idempotencia', 'Chave já utilizada com outro conteúdo'),
    dominio.DadosFinanceirosInconsistentes: (500, 'dados_financeiros_inconsistentes', 'Dados financeiros inconsistentes'),
    p.ConflitoPersistencia: (409, 'conflito_persistencia', 'Conflito ao persistir a operação'),
    p.TransacaoAbortada: (503, 'transacao_abortada', p.TransacaoAbortada.mensagem),
    p.ConfirmacaoIndeterminada: (503, 'confirmacao_indeterminada', p.ConfirmacaoIndeterminada.mensagem),
    p.BancoIndisponivel: (503, 'banco_indisponivel', p.BancoIndisponivel.mensagem),
    p.FalhaPersistencia: (500, 'falha_persistencia', p.FalhaPersistencia.mensagem),
}


class RotaFinanceira(APIRoute):
    """Inclui falhas de dependências; não abre/encerra transações ou sessões."""
    def get_route_handler(self):
        original = super().get_route_handler()

        async def executar(request):
            try:
                return await original(request)
            except (dominio.ErroFinanceiro, p.FalhaPersistencia, SQLAlchemyError) as exc:
                if isinstance(exc, (OperationalError, DisconnectionError, TimeoutError)):
                    exc = p.traduzir_erro(exc)
                status, codigo, mensagem = ERROS.get(type(exc),
                    (500, 'falha_persistencia', p.FalhaPersistencia.mensagem))
                if status >= 500:
                    logger.error('Falha financeira: classe=%s codigo=%s', type(exc).__name__, codigo)
                raise HTTPException(status, {'codigo': codigo, 'mensagem': mensagem}) from None
        return executar
