"""Descontos, cortesias e gratuidade sob a fronteira financeira do PR #56."""
import json
from sqlalchemy import select
from app.models import BeneficioComanda, FechamentoFinanceiroComanda, ItemComanda
from app.schemas.comanda import ItemComandaResponse
from app.schemas.beneficios import EstadoBeneficios, BeneficioPreviaOut, BeneficioOut
from app.services import financeiro as f
from app.services.alteracoes_itens import gestor
from app.services.financeiro_errors import (EntradaFinanceiraInvalida, EstadoFinanceiroIncompativel,
    ComandaFinanceiraNaoEncontrada, SaldoInsuficiente, VersaoItensDesatualizada, ConfirmacaoAjusteNecessaria)
from app.services.regras_financeiras import fingerprint, motivo_auditavel, LIMITE
from app.services.totais_comanda import resumo_totais


def estado(itens, tipo, valor):
    return EstadoBeneficios(itens=itens, desconto_tipo=tipo, desconto_valor=valor,
        **resumo_totais(itens, tipo, valor))


def calcular(db, agendamento, comanda, dados):
    resumo = f._resumo(db, comanda)
    if resumo.situacao != 'aberto' or comanda.status != 'aberta' or agendamento.status == 'cancelado':
        raise EstadoFinanceiroIncompativel('Comanda aberta e financeiramente verificada obrigatória')
    if dados.versao != comanda.versao_itens:
        raise VersaoItensDesatualizada('Versão divergente')
    itens = [ItemComandaResponse.model_validate(i) for i in db.scalars(select(ItemComanda).where(
        ItemComanda.comanda_id == comanda.id, ItemComanda.ativo.is_(True)).order_by(ItemComanda.id)
        .execution_options(populate_existing=True))]
    anterior = estado(itens, comanda.desconto_tipo, comanda.desconto_valor)
    posteriores = itens.copy()
    tipo, valor = comanda.desconto_tipo, comanda.desconto_valor
    if dados.acao == 'item':
        alvo = next((i for i in itens if i.id == dados.item_id), None)
        if alvo is None:
            raise ComandaFinanceiraNaoEncontrada('Serviço ativo não encontrado')
        if alvo.tipo != 'servico':
            raise EntradaFinanceiraInvalida('Benefício individual exige serviço')
        posteriores = [i.model_copy(update={'desconto_tipo':dados.desconto_tipo,
            'desconto_valor':dados.desconto_valor}) if i.id == dados.item_id else i for i in itens]
    elif dados.acao == 'comanda':
        tipo, valor = dados.desconto_tipo, dados.desconto_valor
    try:
        posterior = estado(posteriores, tipo, valor)
    except ValueError as exc:
        raise EntradaFinanceiraInvalida(str(exc)) from None
    if posterior.total > LIMITE:
        raise EntradaFinanceiraInvalida('Total excede limite monetário')
    if posterior.total < resumo.recebido_liquido:
        raise SaldoInsuficiente('Benefício abaixo do recebido líquido')
    gratuito = dados.acao == 'encerramento_gratuito'
    if gratuito:
        if (not itens or any(i.tipo != 'servico' for i in itens)
            or posterior.total != 0 or resumo.recebido_liquido != 0):
            raise EstadoFinanceiroIncompativel('Gratuidade exige serviços ativos, total zero e nenhum recebido líquido')
    elif anterior == posterior:
        raise EntradaFinanceiraInvalida('Nenhuma alteração solicitada')
    exige = posterior.total == resumo.recebido_liquido and resumo.recebido_liquido > 0
    p = BeneficioPreviaOut(comanda_id=comanda.id, versao=comanda.versao_itens,
        anterior=anterior, posterior=posterior, recebido_liquido=resumo.recebido_liquido,
        saldo=posterior.total-resumo.recebido_liquido, exige_fechamento=exige,
        exige_gratuidade=gratuito, conferencia='0'*64)
    fp = fingerprint('previa_beneficio_v1', acao=dados.acao, item_id=dados.item_id,
        motivo=motivo_auditavel(dados.motivo, obrigatorio=True),
        dados=json.dumps(p.model_dump(mode='json', exclude={'conferencia'}), sort_keys=True))
    return p.model_copy(update={'conferencia':fp})


def previa(comanda_id, dados, db, usuario, filial_id=None):
    ator, agenda, comanda = f._contexto(db, usuario, comanda_id, filial_id, leitura=True)
    gestor(ator)
    return calcular(db, agenda, comanda, dados)


def aplicar(comanda_id, dados, chave_idempotencia, db, usuario, filial_id=None):
    with f._escrita(db):
        ator, agenda, comanda = f._contexto(db, usuario, comanda_id, filial_id)
        gestor(ator)
        chave = f.identificador(chave_idempotencia)
        fp = fingerprint('beneficio_v1', dados=json.dumps(dados.model_dump(mode='json'), sort_keys=True))
        original = f._registro(db, BeneficioComanda, comanda, chave_idempotencia=chave)
        if original is not None:
            f._repeticao(original, fp)
            return BeneficioOut.model_validate(original.resultado)
        p = calcular(db, agenda, comanda, dados)
        if p.conferencia != dados.conferencia:
            raise VersaoItensDesatualizada('Valores alterados após prévia')
        if (p.exige_fechamento and not dados.confirmar_fechamento) or (p.exige_gratuidade and not dados.confirmar_gratuidade):
            raise ConfirmacaoAjusteNecessaria('Confirme explicitamente o ajuste/encerramento')
        if dados.acao == 'item':
            item = db.get(ItemComanda, dados.item_id)
            item.desconto_tipo, item.desconto_valor = dados.desconto_tipo, dados.desconto_valor
        elif dados.acao == 'comanda':
            comanda.desconto_tipo, comanda.desconto_valor = dados.desconto_tipo, dados.desconto_valor
        comanda.valor_total = p.posterior.total
        comanda.versao_itens += 1
        from app.services import comissoes
        comissoes.registrar(db, comanda, p.recebido_liquido, 'beneficio', ator.id, chave)
        fechado = p.exige_fechamento or p.exige_gratuidade
        if fechado:
            fechamento = f._inserir(db, FechamentoFinanceiroComanda(comanda_id=comanda.id,
                filial_id=comanda.filial_id, total=p.posterior.total, recebido_liquido=p.recebido_liquido,
                registrado_por=ator.id, motivo=('Encerramento gratuito confirmado: ' if p.exige_gratuidade else 'Quitação por benefício confirmado: ')+dados.motivo.strip(),
                chave_idempotencia=chave, fingerprint=fp), f.FechamentoRegistrado)
            comanda.status, comanda.data_fechamento = 'fechada', fechamento.registrado_em
        resultado = BeneficioOut(**(p.model_dump() | {'versao':comanda.versao_itens}),
            acao=dados.acao, item_id=dados.item_id, motivo=dados.motivo.strip(), registrado_por=ator.id,
            registrado_em=f._agora(db), chave_idempotencia=chave, fechado=fechado)
        registro = BeneficioComanda(comanda_id=comanda.id, filial_id=comanda.filial_id,
            item_id=dados.item_id, registrado_por=ator.id, motivo=dados.motivo.strip(),
            chave_idempotencia=chave, fingerprint=fp, resultado=resultado.model_dump(mode='json'))
        db.add(registro); db.flush(); db.refresh(registro)
        return BeneficioOut.model_validate(registro.resultado)


def historico(comanda_id, db, usuario, filial_id=None):
    _, _, comanda = f._contexto(db, usuario, comanda_id, filial_id, leitura=True)
    rows = db.scalars(select(BeneficioComanda).where(BeneficioComanda.comanda_id == comanda.id)
        .order_by(BeneficioComanda.registrado_em, BeneficioComanda.id))
    return [BeneficioOut.model_validate(r.resultado) for r in rows]
