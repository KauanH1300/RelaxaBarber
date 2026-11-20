from decimal import Decimal
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from app.models.estoque import MovimentoEstoque, ProdutoEstoque
from app.models.insumos_servico import ConsumoAtendimento, InsumoServico
from app.models.agendamento import AgendamentoServico
from app.models.servico import Servico
from app.services.errors import HorarioAgendamentoInvalido, RecursoNaoEncontrado


def listar(db, servico_id, filial_id):
    if db.get(Servico, servico_id) is None:
        raise RecursoNaoEncontrado('Serviço não encontrado')
    return list(db.scalars(select(InsumoServico).where(
        InsumoServico.servico_id == servico_id, InsumoServico.filial_id == filial_id,
    ).order_by(InsumoServico.produto_id)))


def configurar(db, servico_id, filial_id, itens):
    servico = db.scalar(select(Servico).where(Servico.id == servico_id).with_for_update())
    if servico is None:
        raise RecursoNaoEncontrado('Serviço não encontrado')
    ids = [i.produto_id for i in itens]
    if len(ids) != len(set(ids)):
        raise HorarioAgendamentoInvalido('Selecione insumos distintos')
    produtos = db.scalars(select(ProdutoEstoque).where(
        ProdutoEstoque.id.in_(ids), ProdutoEstoque.filial_id == filial_id,
        ProdutoEstoque.consumo.is_(True), ProdutoEstoque.ativo.is_(True),
    ).order_by(ProdutoEstoque.id).with_for_update(read=True).execution_options(populate_existing=True)).all()
    if len(produtos) != len(ids):
        raise HorarioAgendamentoInvalido('Selecione insumos ativos de uso interno desta filial')
    db.execute(delete(InsumoServico).where(
        InsumoServico.servico_id == servico_id, InsumoServico.filial_id == filial_id,
    ))
    db.add_all([InsumoServico(servico_id=servico_id, filial_id=filial_id, **i.model_dump()) for i in itens])


def baixar(db, agendamento, ator):
    # O chamador já mantém o lock do agendamento. A receita usa os serviços
    # registrados na reserva e a configuração vigente na filial.
    demandas = dict(db.execute(select(InsumoServico.produto_id, func.sum(InsumoServico.quantidade))
        .join(AgendamentoServico, AgendamentoServico.servico_id == InsumoServico.servico_id)
        .where(AgendamentoServico.agendamento_id == agendamento.id, InsumoServico.filial_id == agendamento.filial_id)
        .group_by(InsumoServico.produto_id)).all())
    if not demandas:
        return
    produtos = db.scalars(select(ProdutoEstoque).where(
        ProdutoEstoque.filial_id == agendamento.filial_id, ProdutoEstoque.id.in_(demandas),
    ).order_by(ProdutoEstoque.id).with_for_update().execution_options(populate_existing=True))
    for produto in produtos:
        if db.get(ConsumoAtendimento, (agendamento.id, produto.id)) is not None:
            continue
        prevista = demandas[produto.id]
        baixada = min(produto.saldo, prevista) if produto.ativo and produto.consumo else Decimal('0')
        movimento_id = None
        if baixada:
            movimento_id = uuid4()
            saldo = db.execute(update(ProdutoEstoque).where(
                ProdutoEstoque.id == produto.id, ProdutoEstoque.filial_id == agendamento.filial_id,
            ).values(saldo=ProdutoEstoque.saldo - baixada).returning(ProdutoEstoque.saldo)).scalar_one()
            db.add(MovimentoEstoque(
                id=movimento_id, produto_id=produto.id, filial_id=agendamento.filial_id,
                tipo='baixa', quantidade=-baixada, saldo_apos=saldo,
                motivo=f'Consumo interno no atendimento {agendamento.id}',
                registrado_por=ator, chave_idempotencia=uuid4(),
            ))
            db.flush()
        db.add(ConsumoAtendimento(
            agendamento_id=agendamento.id, produto_id=produto.id, filial_id=agendamento.filial_id,
            nome=produto.nome, unidade=produto.unidade, prevista=prevista, baixada=baixada,
            movimento_id=movimento_id, registrado_por=ator,
        ))
