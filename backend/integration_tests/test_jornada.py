"""Concorrência da jornada somente no PostgreSQL local descartável."""
import pytest
from test_contexto_filiais import duas_filiais
from test_concorrencia import data
from test_horarios_filial import corrida, reservar, conferir_reservas


def configurar(db, s, fechado):
    from app.models import Usuario
    from app.schemas.jornada import JornadaUpdate
    from app.services.jornada import atualizar
    dados = JornadaUpdate(dias=[dict(dia_semana=d, fechado=True) if fechado else
        dict(dia_semana=d, fechado=False, hora_inicio='08:00', hora_fim='18:00') for d in range(7)])
    return atualizar(db, db.get(Usuario, s['admin']), s['filial'], s['user'], dados)


@pytest.mark.parametrize('gestao_primeiro', [True, False])
@pytest.mark.parametrize('rollback', [True, False])
def test_primeira_jornada_serializa_com_reserva(runtime_pg, duas_filiais, gestao_primeiro, rollback):
    engine, s = runtime_pg, duas_filiais
    gestao = lambda db: configurar(db, s, True)
    reserva = lambda db: reservar(db, s)
    resultado = corrida(engine, gestao if gestao_primeiro else reserva,
                        reserva if gestao_primeiro else gestao, rollback=rollback)
    assert resultado == ('ok' if rollback else
        'HorarioAgendamentoInvalido' if gestao_primeiro else 'ConflitoGestaoFilial')
    conferir_reservas(engine, 0 if gestao_primeiro != rollback else 1)
