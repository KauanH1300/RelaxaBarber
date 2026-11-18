from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_concorrencia import data
from test_contexto_filiais import duas_filiais
from test_reagendamento import reserva, mover


def test_percentual_fixo_e_transferencia(runtime_pg, pg, reserva):
    from app.models import Usuario, Comanda, ComissaoItem, EventoComissao
    from app.api.routes.comissoes import definir, ExcecaoDados
    s=reserva
    with Session(pg) as db:
        command=db.scalar(select(Comanda).where(Comanda.agendamento_id==s['reserva']))
        original=db.scalar(select(ComissaoItem).where(ComissaoItem.comanda_id==command.id))
        assert original.profissional_id==s['user'] and original.percentual==Decimal('10.00') and original.origem=='padrao'
        comanda_id=command.id
    with Session(runtime_pg) as db:
        definir(s['other'],ExcecaoDados(servico_id=s['service'],percentual=Decimal('35')),s['filial'],db,db.get(Usuario,s['admin']))
        mover(db,s,barbeiro=s['other'])
    with Session(pg) as db:
        atual=db.scalar(select(ComissaoItem).where(ComissaoItem.comanda_id==comanda_id))
        eventos=db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==comanda_id).order_by(EventoComissao.ordem)).all()
        assert atual.profissional_id==s['other'] and atual.percentual==Decimal('35.00') and atual.origem=='excecao'
        assert [(e.profissional_id,e.percentual) for e in eventos]==[(s['user'],Decimal('10.00')),(s['other'],Decimal('35.00'))]
