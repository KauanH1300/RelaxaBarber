from collections import defaultdict

from sqlalchemy import select

from app.models import Agendamento, AgendamentoServico, ClienteFilial, Comanda, ItemComanda, PerfilEnum, Servico, Usuario
from app.models.insumos_servico import ConsumoAtendimento
from app.schemas.linha_tempo_cliente import AtendimentoCliente, AtendimentoClientePago, PaginaAtendimentos
from app.services import filiais, duplicidade_cliente
from app.services.errors import RecursoNaoEncontrado
from app.services.permissoes_agendamento import escopo_consulta
from app.services.resumo_cliente import movimentacoes_financeiras


def consultar(db, usuario, cliente_id, filial_id, pagina, tamanho, incluir_ocorrencias):
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    if not db.scalar(select(ClienteFilial.id).where(
        ClienteFilial.cliente_id == cliente_id, ClienteFilial.filial_id == filial.id,
    )):
        raise RecursoNaoEncontrado('Cliente não encontrado nesta filial')

    estados = ('concluido', 'cancelado', 'nao_compareceu') if incluir_ocorrencias else ('concluido',)
    profissional = escopo_consulta(usuario, None)
    consulta = select(
        Agendamento.id, Agendamento.data, Agendamento.hora_inicio, Usuario.nome.label('profissional'),
        Agendamento.status, Agendamento.observacoes,
    ).join(Usuario, Usuario.id == Agendamento.barbeiro_id).where(
        duplicidade_cliente.filtro_historico(Agendamento.cliente_id, Agendamento.filial_id, cliente_id),
        Agendamento.filial_id == filial.id, Agendamento.status.in_(estados),
    )
    if profissional is not None:
        consulta = consulta.where(Agendamento.barbeiro_id == profissional)
    registros = db.execute(consulta.order_by(Agendamento.data.desc(), Agendamento.hora_inicio.desc(), Agendamento.id.desc())
        .offset((pagina - 1) * tamanho).limit(tamanho + 1)).mappings().all()
    ids = [a['id'] for a in registros[:tamanho]]
    if not ids:
        return PaginaAtendimentos(atendimentos=[], proxima_pagina=None)

    comandas = dict(db.execute(select(Comanda.agendamento_id, Comanda.id).where(
        Comanda.agendamento_id.in_(ids), Comanda.filial_id == filial.id,
        duplicidade_cliente.filtro_historico(Comanda.cliente_id, Comanda.filial_id, cliente_id),
    )).all())
    servicos, produtos, insumos = defaultdict(list), defaultdict(list), defaultdict(list)
    if comandas:
        itens = db.execute(select(Comanda.agendamento_id, ItemComanda.tipo, ItemComanda.descricao, ItemComanda.quantidade)
            .join(ItemComanda, ItemComanda.comanda_id == Comanda.id).where(
                Comanda.id.in_(comandas.values()), ItemComanda.ativo.is_(True),
                ItemComanda.tipo.in_(('servico', 'produto')),
            ).order_by(ItemComanda.id)).all()
        for id_, tipo, nome, quantidade in itens:
            (servicos if tipo == 'servico' else produtos)[id_].append(dict(nome=nome, quantidade=quantidade))

    # Reservas legadas podem não ter comanda. Nesse caso só há os serviços registrados na reserva.
    sem_comanda = set(ids) - comandas.keys()
    if sem_comanda:
        legados = db.execute(select(AgendamentoServico.agendamento_id, Servico.nome)
            .join(Servico, Servico.id == AgendamentoServico.servico_id)
            .where(AgendamentoServico.agendamento_id.in_(sem_comanda)).order_by(AgendamentoServico.id)).all()
        for id_, nome in legados:
            servicos[id_].append(dict(nome=nome, quantidade=1))

    baixas = db.execute(select(ConsumoAtendimento.agendamento_id, ConsumoAtendimento.nome,
        ConsumoAtendimento.unidade, ConsumoAtendimento.baixada).where(
            ConsumoAtendimento.agendamento_id.in_(ids), ConsumoAtendimento.filial_id == filial.id,
            ConsumoAtendimento.baixada > 0,
        ).order_by(ConsumoAtendimento.produto_id)).all()
    for id_, nome, unidade, quantidade in baixas:
        insumos[id_].append(dict(nome=nome, unidade=unidade, quantidade=quantidade))

    totais = {}
    if usuario.perfil == PerfilEnum.ADMIN and comandas:
        totais = {linha['comanda_id']: linha['total_gasto'] for linha in
                  movimentacoes_financeiras(db, cliente_id, [filial.id], comanda_ids=list(comandas.values()))}
    atendimentos = []
    for a in registros[:tamanho]:
        id_ = a['id']
        campos = dict(**a, servicos=servicos[id_], produtos=produtos[id_], insumos=insumos[id_])
        total = totais.get(comandas.get(id_))
        atendimentos.append(AtendimentoClientePago(**campos, total_pago_liquido=total)
                            if total is not None else AtendimentoCliente(**campos))
    return PaginaAtendimentos(atendimentos=atendimentos, proxima_pagina=pagina + 1 if len(registros) > tamanho else None)
