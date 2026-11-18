"""Consultas de comandas, sem alterar estados, itens ou valores financeiros."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import String, case, cast, func, or_
from sqlalchemy.orm import selectinload

from app.models import Agendamento, Cliente, Comanda, Filial, Usuario, PerfilEnum
from app.services.apresentacao_comandas import ABERTAS, ESTADOS, periodo, projetar
from app.schemas.comanda import ComandaResponse, ComandaDetalhe, ComandaPainel
from app.services import filiais
from app.services.errors import AgendamentoInvalido, RecursoNaoEncontrado
from app.services.permissoes_agendamento import escopo_consulta


def consulta(db):
    return (db.query(Comanda, Cliente, Usuario, Agendamento, Filial)
            .outerjoin(Cliente, Cliente.id == Comanda.cliente_id)
            .outerjoin(Usuario, Usuario.id == Comanda.barbeiro_id)
            .outerjoin(Agendamento, Agendamento.id == Comanda.agendamento_id)
            .join(Filial, Filial.id == Comanda.filial_id))


def detalhe(row):
    comanda, cliente, profissional, atendimento, filial, estado, saldo, fechamento = row
    dados = ComandaResponse.model_validate(comanda).model_dump(exclude={'total'})
    dados.update(
        cliente={'id': cliente.id, 'nome': cliente.nome} if cliente else None,
        profissional={'id': profissional.id, 'nome': profissional.nome} if profissional else None,
        filial={'id': filial.id, 'nome': filial.nome},
        atendimento={'id': atendimento.id, 'data': atendimento.data,
                     'hora_inicio': atendimento.hora_inicio, 'hora_fim': atendimento.hora_fim,
                     'status': atendimento.status} if atendimento else None,
        status_apresentacao=estado, saldo_financeiro=saldo, fechamento_financeiro_em=fechamento,
    )
    return ComandaDetalhe(**dados)


def buscar_detalhe(db, usuario, comanda_id: UUID, filial_id: UUID | None):
    usuario = filiais.usuario_atual(db, usuario)
    query = consulta(db).filter(Comanda.id == comanda_id, *filiais.filtro_acesso(usuario, Comanda))
    if filial_id is not None:
        query = query.filter(Comanda.filial_id == filial_id)
    query, estado, saldo, fechamento = projetar(db, query, usuario)
    row = query.add_columns(estado, saldo, fechamento).options(selectinload(Comanda.itens), selectinload(Comanda.cancelamento)).first()
    if row is None:
        raise RecursoNaoEncontrado('Comanda não encontrada')
    return detalhe(row)


def consultar_painel(db, usuario, filial_id, *, pagina=1, tamanho=6, busca='',
                     status=None, status_financeiro=None, profissional_id=None, data_inicio=None, data_fim=None):
    if data_inicio and data_fim and data_inicio > data_fim:
        raise AgendamentoInvalido('A data inicial deve ser anterior ou igual à data final')
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    profissional = escopo_consulta(usuario, profissional_id)
    query = consulta(db).filter(Comanda.filial_id == filial.id)
    if profissional is not None:
        query = query.filter(Comanda.barbeiro_id == profissional)
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

    query, estado, saldo, fechamento = projetar(db, query, usuario)
    query = query.filter(periodo(estado, fechamento, data_inicio, data_fim))
    estados = ('pendente', 'aberta', 'fechada', 'cancelada')
    agregado = query.with_entities(
        *(func.coalesce(func.sum(case((Comanda.status == estado, 1), else_=0)), 0)
          for estado in estados),
        func.coalesce(func.sum(case((estado.in_(ABERTAS), saldo), else_=0)), 0),
        *(func.coalesce(func.sum(case((estado == item, 1), else_=0)), 0) for item in ESTADOS),
    ).one()
    contagens = dict(zip(estados, (int(n) for n in agregado[:4])))
    apresentacao = dict(zip(ESTADOS, (int(n) for n in agregado[5:])))
    if status:
        query = query.filter(Comanda.status == status)
    if status_financeiro:
        query = query.filter(estado == status_financeiro)
    total = query.count()
    rows = (query.add_columns(estado, saldo, fechamento).options(selectinload(Comanda.itens), selectinload(Comanda.cancelamento))
            .order_by(Comanda.created_at.desc(), Comanda.id.desc())
            .offset((pagina - 1) * tamanho).limit(tamanho).all())
    return ComandaPainel(
        itens=[detalhe(row) for row in rows], total=total, pagina=pagina, tamanho=tamanho,
        indicadores={'contagens': contagens,
                     'valor_abertas': Decimal(str(agregado[4])).quantize(Decimal('0.01')),
                     'pagamentos_disponiveis': True, 'contagens_apresentacao': apresentacao,
                     'abertas_verificadas': sum(apresentacao[s] for s in ABERTAS),
                     'aguardando_pagamento': apresentacao['pagamento_pendente'],
                     'fechadas_periodo': apresentacao['fechada'],
                     'escopo_financeiro': 'filial' if usuario.perfil in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO) else 'proprias'},
    )


def listar_comandas(db, usuario, filial_id, status=None):
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    profissional = escopo_consulta(usuario, None)
    query = consulta(db).filter(Comanda.filial_id == filial.id)
    if profissional is not None:
        query = query.filter(Comanda.barbeiro_id == profissional)
    if status:
        query = query.filter(Comanda.status == status)
    query, estado, saldo, fechamento = projetar(db, query, usuario)
    return [detalhe(row) for row in query.add_columns(estado, saldo, fechamento)
            .options(selectinload(Comanda.itens), selectinload(Comanda.cancelamento)).order_by(Comanda.created_at.desc()).all()]
