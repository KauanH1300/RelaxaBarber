"""Agregação e revogação reais no PostgreSQL descartável, sem tabelas financeiras."""
from datetime import time

import pytest
from sqlalchemy import select, event
from sqlalchemy.orm import Session

from test_contexto_filiais import duas_filiais, payload
from test_concorrencia import data


@pytest.mark.parametrize('role,total,scope', [('admin', 3, 'todos'), ('recepcao', 2, 'todos'), ('barbeiro_chefe', 2, 'todos'), ('barbeiro', 1, 'proprio')])
def test_resumo_postgresql_com_duas_unidades_e_sem_escritas(pg, duas_filiais, role, total, scope):
    from app.models import Usuario, UsuarioFilial, AgendamentoServico, Comanda, ItemComanda
    from app.services.agendamento import criar_agendamento
    from app.services.resumo_cliente import consultar_resumo
    from app.services.errors import SemPermissao
    s = duas_filiais
    with Session(pg, autoflush=False) as db:
        admin = db.get(Usuario, s['admin'])
        if role == 'admin':
            user = admin
        elif role == 'barbeiro':
            user = db.get(Usuario, s['other'])
        else:
            user = Usuario(nome=role, email=f'{role}@example.test', senha_hash='ficticio', perfil=role)
            db.add(user)
            db.flush()
            db.add(UsuarioFilial(usuario_id=user.id, filial_id=s['filial']))
            db.commit()
        appointments = []
        for unit, professional, hour, status in (
            (s['filial'], s['user'], 9, 'concluido'),
            (s['filial'], s['other'], 9, 'concluido'),
            (s['second'], s['user'], 10, 'concluido'),
            (s['filial'], s['user'], 11, 'cancelado'),
            (s['second'], s['user'], 12, 'pendente'),
        ):
            dados = payload(s, unit).model_copy(update={'barbeiro_id': professional, 'hora_inicio': time(hour)})
            booking = criar_agendamento(dados, db, admin)
            booking.status = status
            appointments.append(booking)
            db.commit()
        first = appointments[0]
        command = db.scalar(select(Comanda).where(Comanda.agendamento_id == first.id))
        command.valor_total = 98765
        for _ in range(4):
            db.add(AgendamentoServico(agendamento_id=first.id, servico_id=s['service'], preco=200, tempo_estimado=1))
            db.add(ItemComanda(comanda_id=command.id, tipo='produto', descricao='Histórico', quantidade=9, preco_unitario=200))
        db.commit()
        statements = []
        def collect(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)
        event.listen(pg, 'before_cursor_execute', collect)
        try:
            result = consultar_resumo(db, user, s['client'])
            assert result.atendimentos_concluidos == total
            assert result.escopo_profissional == scope
            assert result.parcial is (role != 'admin')
            assert sum(f.atendimentos_concluidos for f in result.filiais) == total
            if role == 'admin':
                money = consultar_resumo(db, user, s['client'], financeiro=True)
                assert money.financeiro_disponivel is False and money.total_gasto is None
                assert all(f.total_gasto is None for f in money.filiais)
            else:
                with pytest.raises(SemPermissao):
                    consultar_resumo(db, user, s['client'], financeiro=True)
            assert all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
        finally:
            event.remove(pg, 'before_cursor_execute', collect)
        if role != 'admin':
            # Outra sessão revoga; o objeto User e o contexto ORM continuam vivos.
            with Session(pg) as external:
                external.query(UsuarioFilial).filter_by(usuario_id=user.id).update({'ativo': False})
                external.commit()
            with pytest.raises(SemPermissao):
                consultar_resumo(db, user, s['client'])
