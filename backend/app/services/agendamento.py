"""Operações de agendamento, sem dependência da camada HTTP.

Cada operação confirma uma única vez pela fronteira transacional compartilhada.
Falhas anteriores ao commit revertem o conjunto; mudanças de estado usam locks
na ordem agendamento, comanda.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.models.agendamento import Agendamento, AgendamentoServico
from app.models.bloqueio_agenda import BloqueioAgenda
from app.models.comanda import Comanda, ItemComanda
from app.models.financeiro import ControleFinanceiroComanda, FechamentoFinanceiroComanda, PagamentoComanda, EstornoPagamento
from app.models.estoque import MovimentoEstoque
from app.models.servico import Servico
from app.models.cliente import Cliente
from app.models.usuario import PERFIS_PROFISSIONAIS, PerfilEnum, Usuario
from app.schemas.valores import validar_preco, validar_duracao
from app.schemas.agendamento import AgendamentoCreate, AgendamentoStatusUpdate, AtendimentoImediatoCreate
from app.services.errors import AgendamentoInvalido, HorarioOcupado, RecursoNaoEncontrado, SemPermissao, HorarioAgendamentoInvalido, ValoresAgendamentoInvalidos, ClienteInativo, ConflitoEstadoAgendamento
from app.services.permissoes_agendamento import (
    PERFIS_GESTAO_AGENDA, escopo_consulta, pode_operar_profissional,
)


from app.services import filiais, clientes as clientes_service, bloqueios_agenda
from app.services.persistencia import transacao_escrita, recarregar_confirmado


FUSO_BARBEARIA = ZoneInfo("America/Recife")


def agora_local() -> datetime:
    """Relógio substituível em testes, independente do fuso do servidor."""
    return datetime.now(FUSO_BARBEARIA)


TRANSICOES = {
    "pendente": {"aguardando", "em_atendimento", "cancelado", "nao_compareceu"},
    "aguardando": {"em_atendimento", "cancelado"},
    "em_atendimento": {"concluido"},
    "concluido": set(),   # estado final
    "cancelado": set(),   # estado final
    "nao_compareceu": set(),
}


def janela_reserva(filial, agora):
    minimo = agora + timedelta(hours=filial.antecedencia_reserva_horas)
    dias = filial.antecedencia_maxima_reserva_dias
    return minimo, agora + timedelta(days=dias) if dias is not None else None


def validar_inicio(data, hora_inicio, *, politica_portal=None):
    if hora_inicio.tzinfo is not None:
        raise HorarioAgendamentoInvalido("Informe o horário local da barbearia, sem fuso no campo hora_inicio")
    inicio = datetime.combine(data, hora_inicio, tzinfo=FUSO_BARBEARIA)
    agora = agora_local()
    if inicio < agora:
        raise HorarioAgendamentoInvalido("Não é permitido criar agendamentos comuns no passado")
    if politica_portal is not None:
        minimo, maximo = janela_reserva(politica_portal, agora)
        if inicio < minimo:
            raise HorarioAgendamentoInvalido(
                f'A filial exige {politica_portal.antecedencia_reserva_horas} h de antecedência para agendar'
            )
        if maximo is not None and inicio > maximo:
            raise HorarioAgendamentoInvalido(
                f'A filial permite agendar com até {politica_portal.antecedencia_maxima_reserva_dias} dias de antecedência'
            )


def pode_cancelar_com_antecedencia(reserva, horas):
    return not horas or datetime.combine(reserva.data, reserva.hora_inicio, tzinfo=FUSO_BARBEARIA) >= (
        agora_local() + timedelta(hours=horas)
    )


def duracao_reservada(reserva):
    inicio = datetime.combine(reserva.data, reserva.hora_inicio)
    fim = datetime.combine(reserva.data, reserva.hora_fim)
    return int((fim - inicio).total_seconds() // 60)


def calcular_termino(data, hora_inicio, total_min):
    try:
        validar_duracao(total_min)
    except ValueError as exc:
        raise ValoresAgendamentoInvalidos("Duração total deve estar entre 1 e 480 minutos") from exc
    inicio = datetime.combine(data, hora_inicio)
    try:
        fim = inicio + timedelta(minutes=total_min)
    except OverflowError as exc:
        raise HorarioAgendamentoInvalido("Término fora dos limites de data suportados") from exc
    if fim.date() != inicio.date():
        raise HorarioAgendamentoInvalido("Agendamento deve terminar antes da meia-noite do mesmo dia")
    return fim.time()


def validar_disponibilidade(db, filial_id, barbeiro_id, data, inicio, fim, ignorar_id=None):
    # Filial e profissional já autorizados e bloqueados pelo chamador.
    from app.services.horarios_filial import validar_agendamento
    from app.services.jornada import validar_agendamento as validar_jornada
    validar_agendamento(db, filial_id, data, inicio, fim)
    validar_jornada(db, filial_id, barbeiro_id, data, inicio, fim)
    query = db.query(Agendamento).filter(
        Agendamento.barbeiro_id == barbeiro_id, Agendamento.data == data,
        Agendamento.status.notin_(('cancelado', 'nao_compareceu')), Agendamento.hora_inicio < fim,
        Agendamento.hora_fim > inicio,
    )
    if ignorar_id is not None:
        query = query.filter(Agendamento.id != ignorar_id)
    if query.first():
        raise HorarioOcupado('Barbeiro já tem agendamento nesse horário')
    if db.scalars(bloqueios_agenda.ativos(filial_id, barbeiro_id, data).where(
        BloqueioAgenda.hora_inicio < fim, BloqueioAgenda.hora_fim > inicio,
    ).limit(1)).first() is not None:
        raise HorarioOcupado('O horário está bloqueado na agenda')


def persistir_reserva(dados, db, filial, criado_por, origem="recepcao"):
    """Nucleo compartilhado; chamador autoriza e mantem a transacao e os locks."""
    # monta os itens, usando o padrão do serviço quando o front não manda valor
    itens = []
    itens_comanda = []
    for s in dados.servicos:
        servico = db.query(Servico).filter(Servico.id == s.servico_id, Servico.ativo == True).with_for_update(read=True).first()
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
    total_min = dados.duracao_min or sum(i.tempo_estimado for i in itens)
    hora_fim = calcular_termino(dados.data, dados.hora_inicio, total_min)
    validar_disponibilidade(db, filial.id, dados.barbeiro_id, dados.data, dados.hora_inicio, hora_fim)
    try:
        valor_total = validar_preco(sum((i.preco for i in itens), Decimal("0.00")))
    except ValueError as exc:
        raise ValoresAgendamentoInvalidos("Total da comanda excede o limite NUMERIC(10,2)") from exc

    agendamento = Agendamento(
        filial_id=filial.id,
        cliente_id=dados.cliente_id,
        barbeiro_id=dados.barbeiro_id,
        data=dados.data,
        hora_inicio=dados.hora_inicio,
        hora_fim=hora_fim,
        status="pendente",
        origem=origem,
        observacoes=dados.observacoes,
        criado_por=criado_por,
        servicos=itens,
    )
    db.add(agendamento)
    db.flush()  # gera o id do agendamento sem finalizar a transação
    clientes_service.garantir_vinculo(db, dados.cliente_id, filial.id)

    comanda = Comanda(
        filial_id=filial.id,
        agendamento_id=agendamento.id,
        cliente_id=dados.cliente_id,
        barbeiro_id=dados.barbeiro_id,
        valor_total=valor_total,
        comissoes_ativas=True,
        status="pendente",
        itens=itens_comanda,
        controle_financeiro=ControleFinanceiroComanda(
            filial_id=filial.id,
            registrado_por=criado_por,
            motivo="Ativação automática na criação do agendamento",
        ) if criado_por is not None else None,
    )
    db.add(comanda)
    db.flush()
    from app.services import comissoes
    for item in itens_comanda: comissoes.fixar(db, comanda, item, dados.barbeiro_id)
    comissoes.registrar(db, comanda, Decimal('0.00'), 'inclusao', criado_por)
    return agendamento


def criar_agendamento(dados: AgendamentoCreate, db: Session, usuario: Usuario) -> Agendamento:
    return _criar_atendimento(dados, db, usuario)


def iniciar_encaixe(dados: AtendimentoImediatoCreate, db: Session, usuario: Usuario) -> Agendamento:
    return _criar_atendimento(dados, db, usuario, imediato=True)


def _criar_atendimento(dados: AgendamentoCreate | AtendimentoImediatoCreate, db: Session,
                      usuario: Usuario, *, imediato=False) -> Agendamento:
    with transacao_escrita(db):
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        if imediato and usuario.perfil not in PERFIS_GESTAO_AGENDA:
            raise SemPermissao('Somente administrador ou recepção pode iniciar um encaixe presencial')
        if not pode_operar_profissional(usuario, dados.barbeiro_id):
            raise SemPermissao("Sem permissão para criar agendamento para outro profissional")
        if usuario.perfil not in PERFIS_GESTAO_AGENDA and any(
            "preco" in item.model_fields_set for item in dados.servicos
        ):
            raise SemPermissao("Sem permissão para sobrescrever preços")
        filial = filiais.resolver_filial(db, usuario, dados.filial_id, bloquear=True)
        if imediato:
            agora = agora_local()
            dados = AgendamentoCreate(**dados.model_dump(), data=agora.date(),
                                       hora_inicio=agora.time().replace(microsecond=0))
        else:
            validar_inicio(dados.data, dados.hora_inicio)
        profissional = db.query(Usuario).filter(
            Usuario.id == dados.barbeiro_id,
            Usuario.ativo.is_(True),
            Usuario.perfil.in_(PERFIS_PROFISSIONAIS),
        ).first()
        if not profissional:
            raise RecursoNaoEncontrado("Profissional ativo não encontrado")
        filiais.validar_profissional(db, dados.barbeiro_id, filial.id)
        if not dados.servicos:
            raise AgendamentoInvalido("Informe pelo menos um serviço")

        cliente = db.query(Cliente).populate_existing().with_for_update(read=True).filter(Cliente.id == dados.cliente_id).first()
        if not cliente:
            raise RecursoNaoEncontrado("Cliente não encontrado")
        if not cliente.ativo:
            raise ClienteInativo("Cliente inativo não pode receber novos agendamentos")

        agendamento = persistir_reserva(dados, db, filial, usuario.id, origem='encaixe' if imediato else 'recepcao')
        if imediato:
            aplicar_status(db, agendamento, AgendamentoStatusUpdate(status='em_atendimento'), registrado_por=usuario.id)
    recarregar_confirmado(db, agendamento)
    return agendamento


def atualizar_status(
    agendamento_id: UUID, dados: AgendamentoStatusUpdate, db: Session, usuario: Usuario,
    filial_id: UUID | None = None,
) -> Agendamento:
    with transacao_escrita(db):
        usuario = filiais.usuario_atual(db, usuario, bloquear=True)
        try:
            filial_informada = filial_id
            filial_id = filiais.filial_do_registro(db, usuario, Agendamento, agendamento_id, escrita=True)
            if filial_informada is not None and filial_informada != filial_id:
                raise RecursoNaoEncontrado("Agendamento não encontrado")
            filial = filiais.resolver_filial(db, usuario, filial_id, bloquear=True)
        except (SemPermissao, RecursoNaoEncontrado):
            raise RecursoNaoEncontrado("Agendamento não encontrado") from None
        # populate_existing relê inclusive entidades já presentes na identity map.
        # Todos os avanços e cancelamentos usam a mesma ordem de locks.
        agendamento = db.query(Agendamento).populate_existing().with_for_update().filter(
            Agendamento.id == agendamento_id, Agendamento.filial_id == filial_id,
        ).first()
        if not agendamento:
            raise RecursoNaoEncontrado("Agendamento não encontrado")
        if not pode_operar_profissional(usuario, agendamento.barbeiro_id):
            raise RecursoNaoEncontrado("Agendamento não encontrado")
        if dados.status == 'nao_compareceu' and usuario.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
            raise SemPermissao('Sem permissão para registrar não comparecimento')
        aplicar_status(db, agendamento, dados, registrado_por=usuario.id)
    recarregar_confirmado(db, agendamento)
    return agendamento


def aplicar_status(db, agendamento, dados, registrado_por=None, registrado_por_cliente=None):
    if dados.status in ('cancelado', 'nao_compareceu'):
        from app.services.reagendamento import _versao
        if _versao(agendamento.atualizado_em) != _versao(dados.atualizado_em_esperado):
            acao = 'cancelar' if dados.status == 'cancelado' else 'registrar a falta'
            raise ConflitoEstadoAgendamento(f'Agendamento alterado. Atualize antes de {acao}')
    if dados.status == agendamento.status:
        if dados.status == 'concluido':
            return
        raise AgendamentoInvalido(f"O agendamento já está '{agendamento.status}'")
    if agendamento.status == "em_atendimento" and dados.status == "cancelado":
        raise ConflitoEstadoAgendamento("Atendimento iniciado não pode ser cancelado pelo fluxo comum")
    if agendamento.status not in TRANSICOES:
        raise ConflitoEstadoAgendamento("Estado do agendamento incompatível com a operação")
    if dados.status not in TRANSICOES[agendamento.status]:
        raise AgendamentoInvalido(
            f"Não é possível mudar de '{agendamento.status}' para '{dados.status}'",
        )
    comanda = db.query(Comanda).populate_existing().with_for_update().filter(
        Comanda.agendamento_id == agendamento.id,
    ).first()
    if not comanda:
        raise ConflitoEstadoAgendamento("Agendamento sem comanda vinculada")
    esperado = {"pendente": "pendente", "aguardando": "aberta", "em_atendimento": "aberta"}
    if (comanda.filial_id, comanda.cliente_id, comanda.barbeiro_id) != (agendamento.filial_id, agendamento.cliente_id, agendamento.barbeiro_id):
        raise ConflitoEstadoAgendamento("Comanda incompatível com o agendamento")
    quitada = db.get(FechamentoFinanceiroComanda, comanda.id) is not None
    if dados.status == 'nao_compareceu':
        registrar_falta(db, agendamento, comanda, dados, registrado_por, quitada)
        return
    # Cancelar a comanda não cancela a reserva. O fluxo comum ainda pode
    # cancelar essa reserva depois, sem reabrir nem sobrescrever a auditoria.
    from app.models import CancelamentoComanda
    cancelada_diretamente = (comanda.status == 'cancelada' and dados.status == 'cancelado'
                            and db.get(CancelamentoComanda, comanda.id) is not None)
    if comanda.status != esperado[agendamento.status] and not (quitada and comanda.status == 'fechada') and not cancelada_diretamente:
        raise ConflitoEstadoAgendamento("Estado da comanda incompatível com o agendamento")

    if dados.status == 'cancelado':
        # O cancelamento comum não pode apagar quitação nem deixar valores
        # recebidos em uma comanda cancelada. Não produz estorno automático.
        pagos = db.scalar(select(func.coalesce(func.sum(PagamentoComanda.valor), 0)).where(PagamentoComanda.comanda_id == comanda.id))
        estornos = db.scalar(select(func.coalesce(func.sum(EstornoPagamento.valor), 0)).where(EstornoPagamento.comanda_id == comanda.id))
        if quitada or pagos > estornos:
            raise ConflitoEstadoAgendamento('Comanda com recebimentos exige tratamento financeiro antes de cancelar')

    agora = datetime.now(timezone.utc)
    agendamento.status = dados.status
    agendamento.atualizado_em = agora
    if dados.status == "cancelado":
        comanda.status = "cancelada"
        agendamento.cancelado_em = agora
        agendamento.cancelado_por = registrado_por
        agendamento.cancelado_por_cliente = registrado_por_cliente
        agendamento.motivo_cancelamento = dados.motivo_cancelamento
        from app.services import comissoes
        comissoes.registrar(db, comanda, Decimal('0.00'), 'cancelamento', registrado_por)
    elif dados.status in ("aguardando", "em_atendimento") and comanda.status == "pendente":
        comanda.status = "aberta"
        comanda.data_abertura = agora
    elif dados.status == 'concluido':
        from app.services import insumos_servico
        insumos_servico.baixar(db, agendamento, registrado_por)
    # A conclusão mantém a comanda e seus registros financeiros intactos.


def registrar_falta(db, agendamento, comanda, dados, ator_id, quitada):
    agora = agora_local()
    termino = datetime.combine(agendamento.data, agendamento.hora_fim, tzinfo=FUSO_BARBEARIA)
    if ator_id is None or agora < termino:
        raise ConflitoEstadoAgendamento('Registre a falta após o término do horário reservado')
    movimentada = any(db.scalar(select(modelo.id).where(modelo.comanda_id == comanda.id).limit(1))
                      for modelo in (PagamentoComanda, MovimentoEstoque))
    if comanda.status != 'pendente' or quitada or movimentada:
        raise ConflitoEstadoAgendamento('A comanda exige tratamento operacional ou financeiro')
    comanda.status = 'cancelada'
    agendamento.status = 'nao_compareceu'
    agendamento.atualizado_em = agora
    agendamento.falta_registrada_em = agora
    agendamento.falta_registrada_por = ator_id
    agendamento.falta_motivo = dados.falta_motivo
    from app.services import comissoes
    comissoes.registrar(db, comanda, Decimal('0.00'), 'nao_comparecimento', ator_id)


def listar_agenda(data: date, barbeiro_id: UUID | None, db: Session, usuario: Usuario, filial_id: UUID | None = None, incluir_cancelados: bool = False):
    usuario = filiais.usuario_atual(db, usuario)
    filial = filiais.resolver_filial(db, usuario, filial_id)
    profissional_id = escopo_consulta(usuario, barbeiro_id)
    query = db.query(Agendamento).filter(
        Agendamento.filial_id == filial.id, Agendamento.data == data,
        *([] if incluir_cancelados else [Agendamento.status != 'cancelado']),
    )
    if profissional_id is not None:
        query = query.filter(Agendamento.barbeiro_id == profissional_id)
    return query.options(selectinload(Agendamento.divergencias_insumos)).order_by(Agendamento.hora_inicio).all()


def buscar_agendamento(agendamento_id, db, usuario, filial_id=None):
    usuario = filiais.usuario_atual(db, usuario)
    query = db.query(Agendamento).filter(
        Agendamento.id == agendamento_id, *filiais.filtro_acesso(usuario, Agendamento),
    )
    if filial_id is not None:
        query = query.filter(Agendamento.filial_id == filial_id)
    registro = query.first()
    if registro is None:
        raise RecursoNaoEncontrado("Agendamento não encontrado")
    return registro
