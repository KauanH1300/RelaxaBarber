from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError, PendingRollbackError


class DriverFailure(Exception):
    def __init__(self, code='23505', constraint='ix_clientes_email', schema='public'):
        self.pgcode = code
        self.diag = SimpleNamespace(constraint_name=constraint, schema_name=schema)
        super().__init__('SEGREDO: senha=nao-expor; SQL interno')


def integrity(code='23505', constraint='ix_clientes_email', schema='public'):
    return IntegrityError('SQL-SECRETO INSERT', {'senha': 'nao-expor'}, DriverFailure(code, constraint, schema))


@pytest.fixture
def persistence(isolated_runtime):
    from app.services import persistencia
    return persistencia


@pytest.mark.parametrize('operation', ['flush', 'commit'])
@pytest.mark.parametrize('code,constraint,conflict', [
    ('23505', 'ix_clientes_email', True),
    ('23505', 'ix_clientes_telefone', True),
    ('23505', 'ix_usuarios_email', True),
    ('23505', 'comandas_agendamento_id_key', True),
    ('23503', 'itens_comanda_servico_id_fkey', True),
    ('23505', 'desconhecida', False),
    ('23503', 'desconhecida', False),
    ('23514', 'desconhecida', False),
    ('23P01', 'constraint_etapa_f_inexistente', False),
])
def test_integridade_rollback_antes_de_propagacao(scenario, persistence, operation, code, constraint, conflict, caplog):
    getattr(scenario.db, operation).side_effect = integrity(code, constraint)
    with pytest.raises(persistence.FalhaPersistencia) as exc:
        scenario.create()
    assert isinstance(exc.value, persistence.ConflitoPersistencia) is conflict
    scenario.db.rollback.assert_called_once()
    assert scenario.db.method_calls[-1][0] == 'rollback'
    scenario.db.refresh.assert_not_called()
    assert 'nao-expor' not in exc.value.mensagem
    assert 'SQL-SECRETO' not in caplog.text
    assert 'nao-expor' not in caplog.text


@pytest.mark.parametrize('phase', ['flush', 'commit'])
def test_falha_de_conexao_distingue_resultado_indeterminado(scenario, persistence, phase):
    getattr(scenario.db, phase).side_effect = OperationalError(None if phase == 'commit' else 'SQL-SECRETO', {}, DriverFailure('08006'))
    with pytest.raises(persistence.BancoIndisponivel) as exc:
        scenario.create()
    assert isinstance(exc.value, persistence.ConfirmacaoIndeterminada) is (phase == 'commit')
    scenario.db.rollback.assert_called_once()


@pytest.mark.parametrize('error', [TypeError('erro de programação'), RuntimeError('erro de programação'), ProgrammingError('SQL-SECRETO', {}, DriverFailure('42601'))])
def test_programacao_nao_e_reclassificada(scenario, error):
    scenario.db.flush.side_effect = error
    with pytest.raises(type(error)) as exc:
        scenario.create()
    assert exc.value is error
    scenario.db.rollback.assert_called_once()
    scenario.db.commit.assert_not_called()


def test_rollback_falha_descarta_sessao_sem_mascarar_erro(scenario, persistence):
    scenario.db.flush.side_effect = integrity()
    scenario.db.rollback.side_effect = OperationalError('SQL-SECRETO', {}, DriverFailure('08006'))
    with pytest.raises(persistence.ConflitoPersistencia):
        scenario.create()
    scenario.db.close.assert_called_once()


def test_erro_em_refresh_nao_promete_desfazer_commit(scenario, persistence):
    scenario.db.refresh.side_effect = OperationalError('SQL-SECRETO', {}, DriverFailure('08006'))
    with pytest.raises(persistence.FalhaLeituraAposCommit) as exc:
        scenario.create()
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()
    assert 'Operação confirmada' in exc.value.mensagem


def test_sessao_bloqueada_recuperada_antes_de_nova_operacao(scenario, persistence):
    failed = False
    original_query = scenario.db.query.side_effect
    def fail():
        nonlocal failed
        failed = True
        raise integrity()
    def query(model):
        if failed:
            raise PendingRollbackError('Sessão precisa de rollback')
        return original_query(model)
    def rollback():
        nonlocal failed
        failed = False
    scenario.db.query.side_effect = query
    scenario.db.flush.side_effect = fail
    scenario.db.rollback.side_effect = rollback
    with pytest.raises(persistence.FalhaPersistencia):
        scenario.create()
    assert not failed
    scenario.db.flush.side_effect = None
    scenario.create()
    scenario.db.commit.assert_called_once()


def test_schema_desconhecido_nao_e_conflito_conhecido(persistence):
    assert type(persistence.traduzir_erro(integrity(schema='outro_schema'))) is persistence.FalhaPersistencia


@pytest.mark.parametrize('state', ['40001', '40P01'])
@pytest.mark.parametrize('phase', ['flush', 'commit'])
def test_abortamento_confirmado_nao_e_conexao_indeterminada(scenario, persistence, state, phase):
    error = OperationalError('SQL-SECRETO', {}, DriverFailure(state), connection_invalidated=True)
    getattr(scenario.db, phase).side_effect = error
    with pytest.raises(persistence.TransacaoAbortada) as exc:
        scenario.create()
    assert not isinstance(exc.value, persistence.ConfirmacaoIndeterminada)
    assert 'abortada' in exc.value.mensagem
    scenario.db.rollback.assert_called_once()
    scenario.db.refresh.assert_not_called()
    assert scenario.db.commit.call_count == (1 if phase == 'commit' else 0)


@pytest.mark.parametrize('state', [None, '57014', '53300', 'XX000'])
def test_operational_sem_evidencia_nao_alega_confirmacao_indeterminada(scenario, persistence, state):
    scenario.db.commit.side_effect = OperationalError('SQL-SECRETO', {}, DriverFailure(state))
    with pytest.raises(persistence.FalhaPersistencia) as exc:
        scenario.create()
    assert type(exc.value) is persistence.FalhaPersistencia
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()


@pytest.mark.parametrize('state', ['08001', '08003', '08004'])
def test_conexao_indisponivel_sem_evidencia_de_commit_enviado(scenario, persistence, state):
    scenario.db.commit.side_effect = OperationalError('SQL-SECRETO', {}, DriverFailure(state))
    with pytest.raises(persistence.BancoIndisponivel) as exc:
        scenario.create()
    assert not isinstance(exc.value, persistence.ConfirmacaoIndeterminada)
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()


@pytest.mark.parametrize('state', ['08000', '08006', '08P01', '08007', '40003', None])
def test_evidencia_de_perda_ou_resultado_desconhecido_no_commit(scenario, persistence, state):
    scenario.db.commit.side_effect = OperationalError(
        None, {}, DriverFailure(state), connection_invalidated=(state is None),
    )
    with pytest.raises(persistence.ConfirmacaoIndeterminada):
        scenario.create()
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()
    scenario.db.refresh.assert_not_called()


def test_sqlstate_alternativo_do_driver(persistence):
    original = DriverFailure(None)
    original.sqlstate = '40P01'
    assert isinstance(persistence.traduzir_erro(OperationalError(None, {}, original), confirmando=True), persistence.TransacaoAbortada)


@pytest.mark.parametrize('error_name', ['TimeoutError', 'DisconnectionError'])
def test_erro_do_pool_nao_indica_commit_enviado(scenario, persistence, error_name):
    from sqlalchemy import exc
    scenario.db.commit.side_effect = getattr(exc, error_name)('Falha de pool simulada')
    with pytest.raises(persistence.BancoIndisponivel) as error:
        scenario.create()
    assert not isinstance(error.value, persistence.ConfirmacaoIndeterminada)
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()


def test_falha_no_flush_implicito_do_commit_nao_e_confirmacao_indeterminada(scenario, persistence):
    scenario.db.commit.side_effect = OperationalError(
        'INSERT SQL-SECRETO', {}, DriverFailure('08006'), connection_invalidated=True,
    )
    with pytest.raises(persistence.BancoIndisponivel) as error:
        scenario.create()
    assert not isinstance(error.value, persistence.ConfirmacaoIndeterminada)
    scenario.db.commit.assert_called_once()
    scenario.db.rollback.assert_called_once()
