"""Operações de agendamento, sem dependência da camada HTTP.

Cada operação mantém o commit único do fluxo original. Tratamento de erros de
integridade, novas validações e proteção concorrente ficam para etapas futuras.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.agendamento import Agendamento, AgendamentoServico
from app.models.comanda import Comanda, ItemComanda
from app.models.servico import Servico
from app.models.usuario import Usuario
from app.schemas.agendamento import AgendamentoCreate, AgendamentoStatusUpdate
from app.services.errors import AgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado


TRANSICOES = {
    "pendente": {"aguardando", "em_atendimento", "cancelado"},
    "aguardando": {"em_atendimento", "cancelado"},
    "em_atendimento": {"concluido", "cancelado"},
    "concluido": set(),   # estado final
    "cancelado": set(),   # estado final
}


def criar_agendamento(dados: AgendamentoCreate, db: Session, usuario: Usuario) -> Agendamento:
    if not dados.servicos:
        raise AgendamentoInvalido("Informe pelo menos um serviço")

    # monta os itens, usando o padrão do serviço quando o front não manda valor
    itens = []
    itens_comanda = []
    for s in dados.servicos:
        servico = db.query(Servico).filter(Servico.id == s.servico_id, Servico.ativo == True).first()
        if not servico:
            raise RecursoNaoEncontrado("Serviço não encontrado")
        itens.append(AgendamentoServico(
            servico_id=servico.id,
            preco=s.preco if s.preco is not None else servico.preco,
            tempo_estimado=s.tempo_estimado if s.tempo_estimado is not None else servico.tempo_estimado,
        ))
        itens_comanda.append(ItemComanda(
            tipo="servico",
            servico_id=servico.id,
            descricao=servico.nome,
            quantidade=1,
            preco_unitario=itens[-1].preco,
        ))
    # calcula o horário de fim
    total_min = sum(i.tempo_estimado for i in itens)
    inicio = datetime.combine(dados.data, dados.hora_inicio)
    hora_fim = (inicio + timedelta(minutes=total_min)).time()

    # impede dois agendamentos sobrepostos para o mesmo barbeiro
    conflito = db.query(Agendamento).filter(
        Agendamento.barbeiro_id == dados.barbeiro_id,
        Agendamento.data == dados.data,
        Agendamento.status != "cancelado",
        Agendamento.hora_inicio < hora_fim,
        Agendamento.hora_fim > dados.hora_inicio,
    ).first()
    if conflito:
        raise HorarioOcupado("Barbeiro já tem agendamento nesse horário")

    agendamento = Agendamento(
        cliente_id=dados.cliente_id,
        barbeiro_id=dados.barbeiro_id,
        data=dados.data,
        hora_inicio=dados.hora_inicio,
        hora_fim=hora_fim,
        status="pendente",
        origem="recepcao",
        observacoes=dados.observacoes,
        criado_por=usuario.id,
        servicos=itens,
    )
    db.add(agendamento)
    db.flush()  # gera o id do agendamento sem finalizar a transação

    comanda = Comanda(
        agendamento_id=agendamento.id,
        cliente_id=dados.cliente_id,
        barbeiro_id=dados.barbeiro_id,
        valor_total=sum(i.preco for i in itens),
        status="pendente",
        itens=itens_comanda,
    )
    db.add(comanda)
    db.commit()
    db.refresh(agendamento)
    return agendamento


def atualizar_status(
    agendamento_id: UUID, dados: AgendamentoStatusUpdate, db: Session,
) -> Agendamento:
    agendamento = db.query(Agendamento).filter(Agendamento.id == agendamento_id).first()
    if not agendamento:
        raise RecursoNaoEncontrado("Agendamento não encontrado")
    if dados.status == agendamento.status:
        raise AgendamentoInvalido(f"O agendamento já está '{agendamento.status}'")
    if dados.status not in TRANSICOES[agendamento.status]:
        raise AgendamentoInvalido(
            f"Não é possível mudar de '{agendamento.status}' para '{dados.status}'",
        )

    agendamento.status = dados.status
    comanda = db.query(Comanda).filter(Comanda.agendamento_id == agendamento.id).first()
    if comanda:
        agora = datetime.now(timezone.utc)

        # cliente chegou (ou começou o atendimento): abre a comanda
        if dados.status in ("aguardando", "em_atendimento") and comanda.status == "pendente":
            comanda.status = "aberta"
            comanda.data_abertura = agora

        # atendimento concluído: fecha a comanda
        if dados.status == "concluido" and comanda.status in ("pendente", "aberta"):
            comanda.status = "fechada"
            comanda.data_fechamento = agora

    db.commit()
    db.refresh(agendamento)
    return agendamento
