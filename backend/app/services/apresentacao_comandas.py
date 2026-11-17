"""Projeção financeira somente leitura: uma linha por comanda, sem conciliar legado."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, case, func, literal, or_

from app.models import (Agendamento, Comanda, ControleFinanceiroComanda,
                        EstornoPagamento, FechamentoFinanceiroComanda,
                        ItemComanda, PagamentoComanda, PerfilEnum)
from app.services.regras_financeiras import FUSO, LIMITE
from app.services.totais_comanda import consulta_totais

ESTADOS = ('pendente', 'aberta', 'pagamento_pendente', 'aguardando_fechamento',
           'fechada', 'cancelada', 'nao_verificado', 'restrito')
ABERTAS = ('aberta', 'pagamento_pendente', 'aguardando_fechamento')


def projetar(db, query, usuario):
    totais = consulta_totais(db).subquery()

    def soma(modelo):
        return db.query(modelo.comanda_id.label('id'), modelo.filial_id.label('filial'),
                        func.sum(modelo.valor).label('valor')).group_by(modelo.comanda_id, modelo.filial_id).subquery()

    pagos, estornos = soma(PagamentoComanda), soma(EstornoPagamento)
    controle, fechamento = ControleFinanceiroComanda, FechamentoFinanceiroComanda
    query = (query.outerjoin(totais, totais.c.id == Comanda.id)
        .outerjoin(controle, and_(controle.comanda_id == Comanda.id, controle.filial_id == Comanda.filial_id))
        .outerjoin(fechamento, and_(fechamento.comanda_id == Comanda.id, fechamento.filial_id == Comanda.filial_id))
        .outerjoin(pagos, and_(pagos.c.id == Comanda.id, pagos.c.filial == Comanda.filial_id))
        .outerjoin(estornos, and_(estornos.c.id == Comanda.id, estornos.c.filial == Comanda.filial_id)))
    zero = Decimal('0.00')
    total = func.coalesce(totais.c.total, zero)
    liquido = func.coalesce(pagos.c.valor, zero) - func.coalesce(estornos.c.valor, zero)
    autorizado = literal(True) if usuario.perfil in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO) else Comanda.barbeiro_id == usuario.id
    valido = and_(controle.comanda_id.is_not(None), total >= zero, total <= LIMITE,
                  func.coalesce(totais.c.invalidos, 0) == 0, liquido >= zero, liquido <= total)
    quitada = and_(valido, fechamento.comanda_id.is_not(None),
                  fechamento.total == total, fechamento.recebido_liquido == liquido, liquido == total)
    incoerente = and_(fechamento.comanda_id.is_not(None), ~quitada)
    estado = case(
        (Comanda.status == 'cancelada', 'cancelada'),
        (~autorizado, 'restrito'),
        (or_(~valido, incoerente), 'nao_verificado'),
        (quitada, 'fechada'),
        (liquido == total, 'aguardando_fechamento'),
        (Agendamento.status == 'concluido', 'pagamento_pendente'),
        (Comanda.status == 'pendente', 'pendente'),
        else_='aberta',
    )
    saldo = case((and_(autorizado, valido, ~incoerente, Comanda.status != 'cancelada'), total - liquido), else_=None)
    data = case((and_(autorizado, quitada, Comanda.status != 'cancelada'), fechamento.registrado_em), else_=None)
    return query, estado, saldo, data


def periodo(estado, fechamento_em, inicio, fim):
    """Fechadas por instante efetivo em Recife; demais por data civil do atendimento."""
    atendimento, fechamento = [], []
    if inicio:
        atendimento.append(Agendamento.data >= inicio)
        fechamento.append(fechamento_em >= datetime.combine(inicio, time.min, FUSO).astimezone(timezone.utc))
    if fim:
        atendimento.append(Agendamento.data <= fim)
        fechamento.append(fechamento_em < datetime.combine(fim + timedelta(days=1), time.min, FUSO).astimezone(timezone.utc))
    return or_(and_(estado == 'fechada', *fechamento), and_(estado != 'fechada', *atendimento))
