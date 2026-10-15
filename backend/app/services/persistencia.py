"""Fronteira transacional das operações de escrita, sem dependência de HTTP."""
from contextlib import contextmanager
import logging

from sqlalchemy.exc import (
    DBAPIError, DisconnectionError, IntegrityError, OperationalError,
    ProgrammingError, SQLAlchemyError, TimeoutError,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class FalhaPersistencia(Exception):
    """Falha não prevista; não transportar mensagens do driver ao cliente."""
    mensagem = "Não foi possível concluir a operação no banco de dados"


class ConflitoPersistencia(FalhaPersistencia):
    def __init__(self, mensagem: str):
        self.mensagem = mensagem
        super().__init__(mensagem)


class BancoIndisponivel(FalhaPersistencia):
    mensagem = "Banco de dados temporariamente indisponível"


class TransacaoAbortada(BancoIndisponivel):
    mensagem = "A transação foi abortada. Nenhuma alteração desta operação foi confirmada"


class ConfirmacaoIndeterminada(BancoIndisponivel):
    mensagem = "Não foi possível confirmar o resultado da operação. Consulte os registros antes de tentar novamente"


class FalhaLeituraAposCommit(FalhaPersistencia):
    mensagem = "Operação confirmada, mas não foi possível carregar o resultado. Consulte os registros antes de tentar novamente"


# Somente restrições nomeadas nas migrações. Nomes não reconhecidos nunca
# recebem automaticamente 409.
CONFLITOS = {
    ("23P01", "ex_agendamentos_profissional_periodo"): "Barbeiro já tem agendamento nesse horário",
    ("23505", "ix_clientes_email"): "Já existe um cliente com esse e-mail",
    ("23505", "ix_clientes_telefone"): "Já existe um cliente com esse telefone",
    ("23505", "ix_usuarios_email"): "E-mail já cadastrado",
    ("23505", "comandas_agendamento_id_key"): "Já existe comanda para esse agendamento",
}
for _nome in (
    "agendamentos_cliente_id_fkey", "agendamentos_barbeiro_id_fkey",
    "agendamentos_cancelado_por_fkey", "agendamentos_criado_por_fkey", "agendamento_servicos_agendamento_id_fkey",
    "agendamento_servicos_servico_id_fkey", "comandas_agendamento_id_fkey",
    "comandas_cliente_id_fkey", "comandas_barbeiro_id_fkey",
    "itens_comanda_comanda_id_fkey", "itens_comanda_servico_id_fkey",
):
    CONFLITOS[("23503", _nome)] = "Um cadastro relacionado não está mais disponível para esta operação"


def reverter(db: Session) -> None:
    """Se nem rollback funcionar, descartar a sessão antes de propagar a falha."""
    try:
        db.rollback()
    except SQLAlchemyError:
        logger.error("Falha ao reverter transação; sessão será fechada")
        try:
            db.close()
        except SQLAlchemyError:
            logger.error("Falha ao fechar sessão de banco")


def traduzir_erro(exc: SQLAlchemyError, *, confirmando: bool = False) -> FalhaPersistencia:
    # Nunca registrar SQL, parâmetros, str(exc) ou traceback contendo o driver.
    logger.error("Falha de persistência: classe=%s", type(exc).__name__)
    if isinstance(exc, IntegrityError):
        original = exc.orig
        diag = getattr(original, "diag", None)
        codigo = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
        nome = getattr(diag, "constraint_name", None)
        schema = getattr(diag, "schema_name", None)
        mensagem = CONFLITOS.get((codigo, nome)) if schema in (None, "public") else None
        if mensagem:
            return ConflitoPersistencia(mensagem)
        return FalhaPersistencia()
    original = getattr(exc, "orig", None)
    codigo = getattr(original, "pgcode", None) or getattr(original, "sqlstate", None)
    # O servidor confirmou o abortamento; prevalece sobre eventual invalidação
    # da conexão. Não confundir com perda da resposta ao COMMIT.
    if isinstance(exc, OperationalError) and codigo in {"40001", "40P01"}:
        return TransacaoAbortada()
    if isinstance(exc, DBAPIError):
        perda_ou_resultado_desconhecido = codigo in {
            "08000", "08006", "08P01", "08007", "40003",
        } or (codigo is None and exc.connection_invalidated)
        if perda_ou_resultado_desconhecido:
            # Session.commit() pode falhar no flush implícito. Havendo uma
            # instrução SQL associada, o erro ocorreu antes do COMMIT DBAPI.
            confirmacao_incerta = confirmando and exc.statement is None
            return ConfirmacaoIndeterminada() if confirmacao_incerta else BancoIndisponivel()
        if isinstance(exc, OperationalError) and codigo in {"08001", "08003", "08004"}:
            # Falha em estabelecer/dispor de conexão: não comprova envio de COMMIT.
            return BancoIndisponivel()
        # Sem SQLSTATE reconhecido ou evidência de desconexão: resposta genérica,
        # sem afirmar sucesso, abortamento conhecido ou confirmação indeterminada.
        return FalhaPersistencia()
    if isinstance(exc, (DisconnectionError, TimeoutError)):
        # Erros do pool não demonstram que o COMMIT foi enviado ao servidor.
        return BancoIndisponivel()
    return FalhaPersistencia()


@contextmanager
def transacao_escrita(db: Session):
    """Usa a transação já iniciada por autenticação/consultas; não abre begin aninhado.

    O chamador não deve fazer commit dentro do bloco. Toda exceção causa limpeza;
    erros de programação e de negócio são propagados sem reclassificação.
    """
    confirmando = False
    try:
        yield
        confirmando = True
        db.commit()
    except Exception as exc:
        reverter(db)
        if isinstance(exc, ProgrammingError):
            raise
        if isinstance(exc, (DBAPIError, DisconnectionError, TimeoutError)):
            raise traduzir_erro(exc, confirmando=confirmando) from exc
        raise


def recarregar_confirmado(db: Session, objeto) -> None:
    """Refresh usa nova transação de leitura; não desfaz commit anterior."""
    try:
        db.refresh(objeto)
    except Exception as exc:
        reverter(db)
        if isinstance(exc, ProgrammingError):
            raise
        if isinstance(exc, SQLAlchemyError):
            logger.error("Falha de leitura após commit: classe=%s", type(exc).__name__)
            raise FalhaLeituraAposCommit() from exc
        raise
