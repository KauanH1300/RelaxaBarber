"""Operações de agendamento, sem dependência da camada HTTP.

Cada operação mantém o commit único do fluxo original. Tratamento de erros de
integridade, novas validações e proteção concorrente ficam para etapas futuras.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models.agendamento import Agendamento, AgendamentoServico
from app.models.comanda import Comanda, ItemComanda
from app.models.servico import Servico
from app.models.cliente import Cliente
from app.models.usuario import PERFIS_PROFISSIONAIS, Usuario
from app.schemas.valores import validar_preco, validar_duracao
from app.schemas.agendamento import AgendamentoCreate, AgendamentoStatusUpdate
from app.services.errors import AgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado, SemPermissao, HorarioAgendamentoInvalido, ValoresAgendamentoInvalidos, ClienteInativo
from app.services.permissoes_agendamento import (
    PERFIS_GESTAO_AGENDA, escopo_consulta, pode_operar_profissional,
)


FUSO_BARBEARIA = ZoneInfo("America/Recife")


def agora_local() -> datetime:
    """Relógio substituível em testes, independente do fuso do servidor."""
    return datetime.now(FUSO_BARBEARIA)


TRANSICOES = {
    "pendente": {"aguardando", "em_atendimento", "cancelado"},
    "aguardando": {"em_atendimento", "cancelado"},
    "em_atendimento": {"concluido", "cancelado"},
    "concluido": set(),   # estado final
    "cancelado": set(),   # estado final
}


def criar_agendamento(dados: AgendamentoCreate, db: Session, usuario: Usuario) -> Agendamento:
    if not pode_operar_profissional(usuario, dados.barbeiro_id):
        raise SemPermissao("Sem permissão para criar agendamento para outro profissional")
    if usuario.perfil not in PERFIS_GESTAO_AGENDA and any(
        "preco" in item.model_fields_set for item in dados.servicos
    ):
        raise SemPermissao("Sem permissão para sobrescrever preços")
    if dados.hora_inicio.tzinfo is not None:
        raise HorarioAgendamentoInvalido("Informe o horário local da barbearia, sem fuso no campo hora_inicio")
    inicio_local = datetime.combine(dados.data, dados.hora_inicio, tzinfo=FUSO_BARBEARIA)
    if inicio_local < agora_local():
        raise HorarioAgendamentoInvalido("Não é permitido criar agendamentos comuns no passado")
    profissional = db.query(Usuario).filter(
        Usuario.id == dados.barbeiro_id,
        Usuario.ativo.is_(True),
        Usuario.perfil.in_(PERFIS_PROFISSIONAIS),
    ).first()
    if not profissional:
        raise RecursoNaoEncontrado("Profissional ativo não encontrado")
    if not dados.servicos:
        raise AgendamentoInvalido("Informe pelo menos um serviço")

    cliente = db.query(Cliente).filter(Cliente.id == dados.cliente_id).first()
    if not cliente:
        raise RecursoNaoEncontrado("Cliente não encontrado")
    if not cliente.ativo:
        raise ClienteInativo("Cliente inativo não pode receber novos agendamentos")

    # monta os itens, usando o padrão do serviço quando o front não manda valor
    itens = []
    itens_comanda = []
    for s in dados.servicos:
        servico = db.query(Servico).filter(Servico.id == s.servico_id, Servico.ativo == True).first()
        if not servico:
            raise RecursoNaoEncontrado("Serviço não encontrado")
        try:
            preco = validar_preco(s.preco if s.preco is not None else servico.preco)
            duracao = validar_duracao(s.tempo_estimado if s.tempo_estimado is not None else servico.tempo_estimado)
        except ValueError as exc:
            raise ValoresAgendamentoInvalidos(str(exc)) from exc
        itens.append(AgendamentoServico(
            servico_id=servico.id,
            preco=preco,
            tempo_estimado=duracao,
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
    try:
        validar_duracao(total_min)
    except ValueError as exc:
        raise ValoresAgendamentoInvalidos("Duração total deve estar entre 1 e 480 minutos") from exc
    inicio = datetime.combine(dados.data, dados.hora_inicio)
    try:
        fim = inicio + timedelta(minutes=total_min)
    except OverflowError as exc:
        raise HorarioAgendamentoInvalido("Término fora dos limites de data suportados") from exc
    if fim.date() != inicio.date():
        raise HorarioAgendamentoInvalido("Agendamento deve terminar antes da meia-noite do mesmo dia")
    hora_fim = fim.time()
    try:
        valor_total = validar_preco(sum((i.preco for i in itens), Decimal("0.00")))
    except ValueError as exc:
        raise ValoresAgendamentoInvalidos("Total da comanda excede o limite NUMERIC(10,2)") from exc

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
        valor_total=valor_total,
        status="pendente",
        itens=itens_comanda,
    )
    db.add(comanda)
    db.commit()
    db.refresh(agendamento)
    return agendamento


def atualizar_status(
    agendamento_id: UUID, dados: AgendamentoStatusUpdate, db: Session, usuario: Usuario,
) -> Agendamento:
    agendamento = db.query(Agendamento).filter(Agendamento.id == agendamento_id).first()
    if not agendamento:
        raise RecursoNaoEncontrado("Agendamento não encontrado")
    if not pode_operar_profissional(usuario, agendamento.barbeiro_id):
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


def listar_agenda(data: date, barbeiro_id: UUID | None, db: Session, usuario: Usuario):
    profissional_id = escopo_consulta(usuario, barbeiro_id)
    query = db.query(Agendamento).filter(
        Agendamento.data == data, Agendamento.status != "cancelado",
    )
    if profissional_id is not None:
        query = query.filter(Agendamento.barbeiro_id == profissional_id)
    return query.order_by(Agendamento.hora_inicio).all()
