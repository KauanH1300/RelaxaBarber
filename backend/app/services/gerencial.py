"""Consultas gerenciais por filial. As operações financeiras continuam nos serviços de origem."""
import csv
import re
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from io import StringIO
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models import Agendamento, Comanda, PerfilEnum, Usuario
from app.models.comissao import EventoComissao
from app.models.financeiro import EstornoPagamento, FechamentoFinanceiroComanda, PagamentoComanda
from app.services import filiais, repasses
from app.services.comissoes_calculo import ratear
from app.services.errors import FilialObrigatoria, SemPermissao
from app.services.financeiro_errors import AcessoFinanceiroNegado, DadosFinanceirosInconsistentes, EntradaFinanceiraInvalida
from app.services.totais_comanda import CENTAVO, ZERO, resumo_totais, subtotal_item


def contexto(db, usuario, filial_id, inicio, fim):
    try:
        ator = filiais.usuario_atual(db, usuario)
        if ator.perfil != PerfilEnum.ADMIN:
            raise SemPermissao()
        filial = filiais.resolver_filial(db, ator, filial_id)
    except (SemPermissao, FilialObrigatoria):
        raise AcessoFinanceiroNegado() from None
    if not 0 <= (fim - inicio).days <= 365 or fim.year == 9999:
        raise EntradaFinanceiraInvalida()
    return filial


def limites(filial, inicio, fim):
    fuso = ZoneInfo(filial.fuso_horario)
    return datetime.combine(inicio, time.min, fuso), datetime.combine(fim + timedelta(days=1), time.min, fuso)


def periodo(dia, granularidade):
    if granularidade == 'mes':
        return dia.replace(day=1)
    if granularidade == 'semana':
        return dia - timedelta(days=dia.weekday())
    return dia


def moeda_media(total, quantidade):
    return (total / quantidade).quantize(CENTAVO, rounding=ROUND_HALF_UP) if quantidade else None


def fatia_financeira(bruto=ZERO, faturado=ZERO, recebido=ZERO, estornos=ZERO):
    return dict(bruto=bruto, faturado=faturado, recebido=recebido, estornos=estornos,
                recebido_liquido=recebido - estornos)


def acumular(destino, valores):
    for chave, valor in valores.items():
        destino[chave] += valor


def apurar(fechamentos, caixa, agenda, fuso, granularidade):
    total = fatia_financeira()
    series = defaultdict(fatia_financeira)
    profissionais = defaultdict(lambda: dict(fatia_financeira(), concluidos=0))
    ranking = {}
    valor_ticket = ZERO
    base_ticket = 0
    for fechamento, comanda in fechamentos:
        try:
            calculo = resumo_totais(comanda.itens, comanda.desconto_tipo, comanda.desconto_valor)
        except ValueError:
            raise DadosFinanceirosInconsistentes() from None
        if calculo['total'] != fechamento.total:
            raise DadosFinanceirosInconsistentes()
        valores = fatia_financeira(bruto=calculo['total_bruto'], faturado=fechamento.total)
        dia = fechamento.registrado_em.astimezone(fuso).date()
        acumular(total, valores)
        acumular(series[periodo(dia, granularidade)], valores)
        acumular(profissionais[comanda.barbeiro_id], valores)
        if comanda.tipo == 'agendada':
            valor_ticket += fechamento.total
            base_ticket += 1

        ativos = [item for item in comanda.itens if item.ativo]
        bases = {item.id: subtotal_item(item) for item in ativos}
        abatimentos = ratear(calculo['desconto_geral'], bases)
        for item in ativos:
            if item.tipo != 'servico':
                continue
            chave = item.servico_id or item.descricao
            linha = ranking.setdefault(chave, dict(id=str(chave), nome=item.descricao, quantidade=0, faturado=ZERO))
            linha['quantidade'] += item.quantidade
            linha['faturado'] += bases[item.id] - abatimentos[item.id]

    for profissional, dia, recebido, estornos in caixa:
        valores = fatia_financeira(recebido=recebido, estornos=estornos)
        acumular(total, valores)
        acumular(series[periodo(dia, granularidade)], valores)
        acumular(profissionais[profissional], valores)

    estados = Counter(a.status for a in agenda)
    concluidos = [a for a in agenda if a.status == 'concluido']
    for atendimento in concluidos:
        profissionais[atendimento.barbeiro_id]['concluidos'] += 1
    return {
        'indicadores': dict(total, concluidos=len(concluidos), clientes=len({a.cliente_id for a in concluidos}),
                            cancelados=estados['cancelado'], faltas=estados['nao_compareceu'], agendamentos=len(agenda),
                            taxa_cancelamento=moeda_media(Decimal(estados['cancelado'] * 100), len(agenda)),
                            taxa_falta=moeda_media(Decimal(estados['nao_compareceu'] * 100), len(agenda)),
                            ticket_medio=moeda_media(valor_ticket, base_ticket), base_ticket=base_ticket),
        'periodos': [dict(valores, periodo=dia) for dia, valores in sorted(series.items())],
        'dias': dict(sorted(Counter(a.data.weekday() for a in concluidos).items())),
        'horarios': dict(sorted(Counter(a.hora_inicio.hour for a in concluidos).items())),
        'servicos': list(ranking.values()),
        'profissionais': profissionais,
    }


def consulta_caixa(db, filtros, desde, ate, fuso):
    for modelo, instante in ((PagamentoComanda, PagamentoComanda.recebido_em),
                             (EstornoPagamento, EstornoPagamento.efetivado_em)):
        dia = func.date(func.timezone(fuso, instante))
        stmt = (select(Comanda.barbeiro_id, dia, func.sum(modelo.valor))
                .join(Comanda, (Comanda.id == modelo.comanda_id) & (Comanda.filial_id == modelo.filial_id))
                .where(*filtros, instante >= desde, instante < ate)
                .group_by(Comanda.barbeiro_id, dia))
        for profissional, data, valor in db.execute(stmt):
            yield profissional, data, valor if modelo is PagamentoComanda else ZERO, valor if modelo is EstornoPagamento else ZERO


def consultar(db, filial, inicio, fim, profissional_id, granularidade, busca, ordem, ordem_equipe):
    desde, ate = limites(filial, inicio, fim)
    filtros = [Comanda.filial_id == filial.id]
    agenda = select(Agendamento).where(Agendamento.filial_id == filial.id, Agendamento.data.between(inicio, fim))
    eventos = select(EventoComissao.profissional_id).where(EventoComissao.filial_id == filial.id).distinct()
    if profissional_id:
        filtros.append(Comanda.barbeiro_id == profissional_id)
        agenda = agenda.where(Agendamento.barbeiro_id == profissional_id)
        eventos = eventos.where(EventoComissao.profissional_id == profissional_id)

    fechamento = FechamentoFinanceiroComanda
    stmt = (select(fechamento, Comanda)
            .join(Comanda, (Comanda.id == fechamento.comanda_id) & (Comanda.filial_id == fechamento.filial_id))
            .where(*filtros, fechamento.registrado_em >= desde, fechamento.registrado_em < ate)
            .options(selectinload(Comanda.itens))
            .order_by(fechamento.registrado_em, Comanda.id))
    resultado = apurar(db.execute(stmt).all(), consulta_caixa(db, filtros, desde, ate, filial.fuso_horario),
                       db.scalars(agenda).all(), desde.tzinfo, granularidade)
    comissoes = dict(gerada=ZERO, liberada=ZERO, elegivel=ZERO, paga=ZERO)
    for profissional in db.scalars(eventos):
        resumo = repasses.resumo_por_origem(db, filial.id, profissional, inicio, fim)
        acumular(comissoes, resumo)
        resultado['profissionais'][profissional].update(resumo)
    desempenho = resultado['profissionais']
    ids = [pid for pid in desempenho if pid is not None]
    nomes = dict(db.execute(select(Usuario.id, Usuario.nome).where(Usuario.id.in_(ids))).all()) if ids else {}
    resultado['profissionais'] = [
        dict(dict.fromkeys(comissoes, ZERO) | linha, id=pid, nome=nomes.get(pid, 'Sem profissional'))
        for pid, linha in desempenho.items()
    ]
    resultado['profissionais'].sort(key=lambda linha: (-linha[ordem_equipe], linha['nome'].casefold(), str(linha['id'])))
    resultado['comissoes'] = comissoes
    resultado['servicos'] = sorted(
        (linha for linha in resultado['servicos'] if busca.strip().casefold() in linha['nome'].casefold()),
        key=lambda linha: (-linha[ordem], linha['nome'].casefold(), linha['id']),
    )
    return resultado


def exportar(resultado, *, filial, inicio, fim, profissional_id, granularidade, busca, ordem, ordem_equipe):
    arquivo = StringIO(newline='')
    escritor = csv.writer(arquivo, delimiter=';')

    def linha(valores):
        escritor.writerow([
            "'" + v if isinstance(v, str) and re.match(r'^[\s\x00-\x1f\ufeff]*[=+\-@]', v)
            else v for v in valores
        ])

    linha(['Filial', filial.nome, 'Identificador', filial.id])
    linha(['Período inicial', inicio, 'Período final', fim])
    linha(['Profissional', profissional_id or 'Todos', 'Agrupamento', granularidade])
    linha(['Busca de serviços', busca, 'Ordenação dos serviços', ordem])
    linha(['Ordenação do desempenho', ordem_equipe])
    for secao in ('indicadores', 'comissoes', 'periodos', 'servicos', 'profissionais', 'dias', 'horarios'):
        linha([])
        linha([secao])
        dados = resultado[secao]
        if isinstance(dados, dict):
            for chave, valor in dados.items():
                linha([chave, valor])
        elif dados:
            campos = tuple(dados[0])
            linha(campos)
            for registro in dados:
                linha([registro[campo] for campo in campos])
    return '\ufeff' + arquivo.getvalue()

