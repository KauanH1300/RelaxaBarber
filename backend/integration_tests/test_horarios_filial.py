"""Opt-in no PostgreSQL descartável da fixture pg; nunca executar no Supabase."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from test_contexto_filiais import duas_filiais, payload
from test_concorrencia import data
from test_cancelamento_etapa_g import wait_for_lock


@pytest.mark.parametrize('gestao_primeiro', [True, False])
def test_configuracao_e_criacao_serializam_na_filial(pg, duas_filiais, gestao_primeiro):
    from app.models import Usuario, Agendamento, FilialHorario
    from app.schemas.horario_filial import HorariosFilialUpdate
    from app.services.agendamento import criar_agendamento
    from app.services.horarios_filial import atualizar
    from app.services.errors import ConflitoGestaoFilial, HorarioAgendamentoInvalido
    s = duas_filiais
    ready, release, started = Event(), Event(), Event()
    pid = []
    class Paused(Session):
        def commit(self):
            self.flush()
            ready.set()
            assert release.wait(5)
            return super().commit()
    def operate(db, management):
        if management:
            dados = HorariosFilialUpdate(dias=[{'dia_semana': d, 'fechado': True} for d in range(7)])
            atualizar(db, db.get(Usuario, s['admin']), s['filial'], dados)
        else:
            criar_agendamento(payload(s, s['filial']), db, db.get(Usuario, s['user']))
    def first():
        with Paused(pg, autoflush=False) as db:
            operate(db, gestao_primeiro)
    def second():
        with Session(pg, autoflush=False) as db:
            db.execute(text("SET LOCAL statement_timeout='8s'"))
            pid.append(db.scalar(text('SELECT pg_backend_pid()')))
            started.set()
            with pytest.raises(HorarioAgendamentoInvalido if gestao_primeiro else ConflitoGestaoFilial):
                operate(db, not gestao_primeiro)
            assert db.scalar(text('SELECT 1')) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(first)
        try:
            assert ready.wait(3)
            two = pool.submit(second)
            assert started.wait(3)
            wait_for_lock(pg, pid[0])
        finally:
            release.set()
        one.result(timeout=10)
        two.result(timeout=10)
    with Session(pg) as db:
        assert db.query(Agendamento).count() == (0 if gestao_primeiro else 1)
        assert db.query(FilialHorario).count() == (7 if gestao_primeiro else 0)
