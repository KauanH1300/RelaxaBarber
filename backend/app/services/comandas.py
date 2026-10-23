"""Consultas de comandas, sem alterar estados, itens ou valores financeiros."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import String, case, cast, func, or_
from sqlalchemy.orm import selectinload

from app.models import Agendamento, Cliente, Comanda, Filial, ItemComanda, Usuario
from app.schemas.comanda import ComandaResponse, ComandaDetalhe, ComandaPainel
from app.services import filiais
from app.services.errors import AgendamentoInvalido, RecursoNaoEncontrado
from app.services.permissoes_agendamento import escopo_consulta


def consulta(db):
    return (db.query(Comanda, Cliente, Usuario, Agendamento, Filial)
            .join(Cliente, Cliente.id == Comanda.cliente_id)
            .join(Usuario, Usuario.id == Comanda.barbeiro_id)
            .join(Agendamento, Agendamento.id == Comanda.agendamento_id)
            .join(Filial, Filial.id == Comanda.filial_id))


def detalhe(row):
    comanda, cliente, profissional, atendimento, filial = row
    dados = ComandaResponse.model_validate(comanda).model_dump(exclude={'total'})
    dados.update(
        cliente={'id': cliente.id, 'nome': cliente.nome},
        profissional={'id': profissional.id, 'nome': profissional.nome},
        filial={'id': filial.id, 'nome': filial.nome},
        atendimento={'id': atendimento.id, 'data': atendimento.data,
                     'hora_inicio': atendimento.hora_inicio, 'hora_fim': atendimento.hora_fim,
                     'status': atendimento.status},
    )
    return ComandaDetalhe(**dados)


def buscar_detalhe(db, usuario, comanda_id: UUID, filial_id: UUID | None):
    usuario = filiais.usuario_atual(db, usuario)
    query = consulta(db).filter(Comanda.id == comanda_id, *filiais.filtro_acesso(usuario, Comanda))
    if filial_id is not None:
        query = query.filter(Comanda.filial_id == filial_id)
    row = query.options(selectinload(Comanda.itens)).first()
    if row is None:
        raise RecursoNaoEncontrado('Comanda não encontrada')
    return detalhe(row)


def consultar_painel(db, usuario, filial_id, *, pagina=1, tamanho=6, busca='',
                     status=None, profissional_id=None, data_inicio=None, data_fim=None):
    if data_inicio and data_fim and data_inicio > data_fim:
        raise AgendamentoInvalido('A data inicial deve ser anterior ou igual à data final')
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    profissional = escopo_consulta(usuario, profissional_id)
    query = consulta(db).filter(Comanda.filial_id == filial.id)
    if profissional is not None:
        query = query.filter(Comanda.barbeiro_id == profissional)
    if data_inicio:
        query = query.filter(Agendamento.data >= data_inicio)
    if data_fim:
        query = query.filter(Agendamento.data <= data_fim)
    if busca.strip():
        # % e _ são caracteres literais, não curingas fornecidos pelo usuário.
        termo = busca.strip().lower()
        def literal(value):
            return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(or_(
            func.lower(Cliente.nome).like(f'%{literal(termo)}%', escape='\\'),
            func.replace(cast(Comanda.id, String), '-', '').like(
                f'%{literal(termo.replace("-", ""))}%', escape='\\'),
        ))

    # Uma linha por comanda: itens nunca multiplicam as contagens/indicadores.
    totais = db.query(ItemComanda.comanda_id.label('id'),
                      func.sum(ItemComanda.quantidade * ItemComanda.preco_unitario).label('total'))\
        .group_by(ItemComanda.comanda_id).subquery()
    estados = ('pendente', 'aberta', 'fechada', 'cancelada')
    agregado = query.outerjoin(totais, totais.c.id == Comanda.id).with_entities(
        *(func.coalesce(func.sum(case((Comanda.status == estado, 1), else_=0)), 0)
          for estado in estados),
        func.coalesce(func.sum(case((Comanda.status == 'aberta', totais.c.total), else_=0)), 0),
    ).one()
    contagens = dict(zip(estados, (int(n) for n in agregado[:4])))
    if status:
        query = query.filter(Comanda.status == status)
    total = query.count()
    rows = (query.options(selectinload(Comanda.itens))
            .order_by(Comanda.created_at.desc(), Comanda.id.desc())
            .offset((pagina - 1) * tamanho).limit(tamanho).all())
    return ComandaPainel(
        itens=[detalhe(row) for row in rows], total=total, pagina=pagina, tamanho=tamanho,
        indicadores={'contagens': contagens,
                     'valor_abertas': Decimal(str(agregado[4])).quantize(Decimal('0.01')),
                     'pagamentos_disponiveis': False},
    )
