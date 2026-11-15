"""Estados e rollback com SQLite em memória; não substitui concorrência PostgreSQL."""
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError


@pytest.fixture
def concluida(memory_session, models, schemas, monkeypatch):
    from app.services import agendamento, financeiro
    db = memory_session
    user = models.Usuario(nome='Teste', email='estados@example.test', senha_hash='ficticio', perfil=models.PerfilEnum.BARBEIRO)
    filial = models.Filial(nome='Teste', empresa=models.Empresa(nome='Teste'))
    cliente = models.Cliente(nome='Teste', telefone='00000000000')
    servico = models.Servico(nome='Corte', preco=30, tempo_estimado=30, comissao_padrao=0)
    db.add_all([models.UsuarioFilial(usuario=user, filial=filial), cliente, servico])
    db.commit()
    a = agendamento.criar_agendamento(schemas.AgendamentoCreate(
        cliente_id=cliente.id, barbeiro_id=user.id, filial_id=filial.id,
        data=date(2099, 1, 1), hora_inicio=time(9), servicos=[{'servico_id': servico.id}]), db, user)
    c = db.scalar(select(models.Comanda).where(models.Comanda.agendamento_id == a.id))
    for estado in ('em_atendimento', 'concluido'):
        agendamento.atualizar_status(a.id, schemas.AgendamentoStatusUpdate(status=estado), db, user)
    # SQLite não oferece os locks/isolamento PostgreSQL; autorização tem suíte própria.
    monkeypatch.setattr(financeiro, '_contexto', lambda *args, **kwargs: (user, a, c))
    monkeypatch.setattr(financeiro, '_agora', lambda db: datetime.now(timezone.utc))
    return db, a, c, user


def pagar(db, c, user, valor):
    # Fixture de quitação histórica; pagamentos avulsos novos são proibidos.
    from app.models import PagamentoComanda
    from app.services.regras_financeiras import fingerprint
    dados = dict(valor=Decimal(valor), forma='pix', recebido_em=datetime.now(timezone.utc))
    p = PagamentoComanda(comanda_id=c.id, filial_id=c.filial_id, registrado_por=user.id,
        chave_idempotencia=uuid4(), fingerprint=fingerprint('pagamento', comanda_id=c.id, **dados), **dados)
    db.add(p)
    db.commit()
    return p


def test_conclusao_nao_fecha_e_quitacao_sozinha_nao_fecha(concluida):
    db, a, c, user = concluida
    assert a.status == 'concluido' and c.status == 'aberta'
    assert c.data_fechamento is None
    pagar(db, c, user, '30.00')
    db.refresh(c)
    assert c.status == 'aberta' and c.data_fechamento is None


def test_saldo_pendente_nao_fecha(concluida, models):
    from app.services.financeiro import fechar_comanda
    from app.services.financeiro_errors import SaldoInsuficiente
    db, a, c, user = concluida
    pagar(db, c, user, '10.00')
    with pytest.raises(SaldoInsuficiente):
        fechar_comanda(c.id, chave_idempotencia=uuid4(), db=db, usuario=user)
    db.refresh(c)
    assert c.status == 'aberta' and c.data_fechamento is None
    assert db.scalar(select(models.FechamentoFinanceiroComanda)) is None


@pytest.mark.parametrize('historica', [False, True])
def test_fechamento_quitado_e_replay_preservam_data(concluida, historica):
    from app.services.financeiro import fechar_comanda
    db, a, c, user = concluida
    if historica:
        c.status = 'fechada'
        c.data_fechamento = datetime(2020, 1, 1)
        db.commit()
    data_antiga = c.data_fechamento
    pagar(db, c, user, '30.00')
    chave = uuid4()
    resultado = fechar_comanda(c.id, chave_idempotencia=chave, db=db, usuario=user)
    db.refresh(c)
    assert c.status == 'fechada'
    assert c.data_fechamento == (data_antiga if historica else resultado.registrado_em)
    data = c.data_fechamento
    fechar_comanda(c.id, chave_idempotencia=chave, db=db, usuario=user)
    db.refresh(c)
    assert c.data_fechamento == data


def test_falha_commit_reverte_fechamento_e_estado(concluida, models):
    from app.services.financeiro import fechar_comanda
    from app.services.persistencia import FalhaPersistencia
    db, a, c, user = concluida
    pagar(db, c, user, '30.00')
    def falhar(session):
        session.flush()
        raise IntegrityError('falha simulada', {}, Exception('teste'))
    event.listen(db, 'before_commit', falhar)
    try:
        with pytest.raises(FalhaPersistencia):
            fechar_comanda(c.id, chave_idempotencia=uuid4(), db=db, usuario=user)
    finally:
        event.remove(db, 'before_commit', falhar)
    db.refresh(c)
    assert c.status == 'aberta' and c.data_fechamento is None
    assert db.scalar(select(models.FechamentoFinanceiroComanda)) is None
    assert db.scalar(select(models.PagamentoComanda)) is not None
