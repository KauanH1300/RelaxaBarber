"""Prévia sem escrita e aplicação atômica sob os locks do núcleo financeiro."""
import json
from sqlalchemy import select
from app.models import ItemComanda, Servico, PerfilEnum, AlteracaoItemComanda, FechamentoFinanceiroComanda
from app.schemas.comanda import ItemComandaResponse
from app.schemas.itens_comanda import PreviaAlteracaoOut, AlteracaoItemOut
from app.services import financeiro as f
from app.services.financeiro_errors import (AcessoFinanceiroNegado, ComandaFinanceiraNaoEncontrada,
    EntradaFinanceiraInvalida, EstadoFinanceiroIncompativel, HistoricoFinanceiroNaoVerificado,
    SaldoInsuficiente, VersaoItensDesatualizada, ConfirmacaoAjusteNecessaria)
from app.services.regras_financeiras import fingerprint, valor_monetario, LIMITE, motivo_auditavel
from app.services.totais_comanda import resumo_totais


def gestor(ator):
    if ator.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
        raise AcessoFinanceiroNegado('Somente gestão autorizada pode ajustar serviços')


def calcular(db, agendamento, comanda, item_id, dados):
    resumo = f._resumo(db, comanda)
    if resumo.situacao == 'nao_verificado':
        raise HistoricoFinanceiroNaoVerificado('Controle financeiro obrigatório')
    if resumo.situacao != 'aberto' or comanda.status != 'aberta' or agendamento.status == 'cancelado':
        raise EstadoFinanceiroIncompativel('Somente comandas abertas e verificadas aceitam ajustes')
    if dados.versao != comanda.versao_itens:
        raise VersaoItensDesatualizada('Versão divergente')
    item = db.scalar(select(ItemComanda).where(ItemComanda.id == item_id,
        ItemComanda.comanda_id == comanda.id).execution_options(populate_existing=True))
    if item is None:
        raise ComandaFinanceiraNaoEncontrada('Item não encontrado nesta comanda')
    if not item.ativo or item.tipo != 'servico':
        raise EstadoFinanceiroIncompativel('Serviço ativo obrigatório')
    anterior = ItemComandaResponse.model_validate(item)
    novo = anterior.model_dump(exclude={'subtotal'})
    if dados.acao == 'remover':
        novo['ativo'] = False
    else:
        novo['quantidade'] = dados.quantidade
        if dados.acao == 'substituir':
            servico = db.scalar(select(Servico).where(Servico.id == dados.servico_id)
                .with_for_update(read=True).execution_options(populate_existing=True))
            if servico is None or not servico.ativo:
                raise EntradaFinanceiraInvalida('Serviço cadastrado ativo obrigatório')
            novo.update(servico_id=servico.id, descricao=servico.nome,
                preco_unitario=valor_monetario(servico.preco, permitir_zero=True))
            if servico.id != item.servico_id:
                novo.update(desconto_tipo='nenhum', desconto_valor=f.ZERO)
    try:
        posterior = ItemComandaResponse.model_validate(novo)
        itens = db.scalars(select(ItemComanda).where(ItemComanda.comanda_id == comanda.id,
            ItemComanda.ativo.is_(True)).execution_options(populate_existing=True)).all()
        projetados = [posterior if i.id == item.id else i for i in itens]
        total = resumo_totais(projetados, comanda.desconto_tipo, comanda.desconto_valor)['total']
    except ValueError as exc:
        raise EntradaFinanceiraInvalida(str(exc)) from None
    if anterior == posterior:
        raise EntradaFinanceiraInvalida('Nenhuma alteração solicitada')
    if total > LIMITE:
        raise EntradaFinanceiraInvalida('Total excede limite monetário')
    if total < resumo.recebido_liquido:
        raise SaldoInsuficiente('Ajuste abaixo do valor líquido recebido')
    exige = total == resumo.recebido_liquido and resumo.recebido_liquido > 0
    contexto = dict(comanda_id=comanda.id, item_id=item.id, versao=comanda.versao_itens,
        anterior=anterior, posterior=posterior, total_anterior=resumo.total, total=total,
        recebido_liquido=resumo.recebido_liquido, saldo=total-resumo.recebido_liquido,
        exige_fechamento=exige, conferencia='0'*64)
    previa = PreviaAlteracaoOut(**contexto)
    conferencia = fingerprint('previa_ajuste_itens_v1', acao=dados.acao,
        motivo=motivo_auditavel(dados.motivo, obrigatorio=True),
        dados=json.dumps(previa.model_dump(mode='json', exclude={'conferencia'}), sort_keys=True))
    return item, previa.model_copy(update={'conferencia':conferencia})


def previa(comanda_id, item_id, dados, db, usuario, filial_id=None):
    ator, agendamento, comanda = f._contexto(db, usuario, comanda_id, filial_id, leitura=True)
    gestor(ator)
    return calcular(db, agendamento, comanda, item_id, dados)[1]


def aplicar(comanda_id, item_id, dados, chave_idempotencia, db, usuario, filial_id=None):
    with f._escrita(db):
        ator, agendamento, comanda = f._contexto(db, usuario, comanda_id, filial_id)
        gestor(ator)
        chave = f.identificador(chave_idempotencia)
        esperado = fingerprint('ajuste_item_v1', item_id=item_id,
            dados=json.dumps(dados.model_dump(mode='json'), sort_keys=True))
        original = f._registro(db, AlteracaoItemComanda, comanda, chave_idempotencia=chave)
        if original is not None:
            f._repeticao(original, esperado)
            return AlteracaoItemOut.model_validate(original.resultado)
        item, p = calcular(db, agendamento, comanda, item_id, dados)
        if p.conferencia != dados.conferencia:
            raise VersaoItensDesatualizada('Valores ou catálogo alterados após prévia')
        if p.exige_fechamento and dados.confirmar_fechamento is not True:
            raise ConfirmacaoAjusteNecessaria('Confirmação explícita de quitação necessária')
        for campo in ['quantidade','servico_id','descricao','preco_unitario','ativo','desconto_tipo','desconto_valor']:
            setattr(item, campo, getattr(p.posterior, campo))
        comanda.versao_itens += 1
        comanda.valor_total = p.total
        agora = f._agora(db)
        if p.exige_fechamento:
            fechamento = f._inserir(db, FechamentoFinanceiroComanda(comanda_id=comanda.id, filial_id=comanda.filial_id,
                total=p.total, recebido_liquido=p.recebido_liquido,
                motivo='Quitação por ajuste confirmado: '+dados.motivo.strip(), registrado_por=ator.id,
                chave_idempotencia=chave, fingerprint=esperado), f.FechamentoRegistrado)
            comanda.status = 'fechada'
            comanda.data_fechamento = fechamento.registrado_em
        resultado = AlteracaoItemOut(**(p.model_dump() | {'versao':comanda.versao_itens}),
            acao=dados.acao, motivo=dados.motivo.strip(), registrado_em=agora, registrado_por=ator.id,
            chave_idempotencia=chave, fechado=p.exige_fechamento)
        registro = AlteracaoItemComanda(comanda_id=comanda.id, filial_id=comanda.filial_id, item_id=item.id,
            registrado_por=ator.id, motivo=dados.motivo.strip(), chave_idempotencia=chave,
            fingerprint=esperado, resultado=resultado.model_dump(mode='json'))
        db.add(registro)
        db.flush()
        db.refresh(registro)
        resultado = AlteracaoItemOut.model_validate(registro.resultado)
    return resultado


def historico(comanda_id, db, usuario, filial_id=None):
    _, _, comanda = f._contexto(db, usuario, comanda_id, filial_id, leitura=True)
    registros = db.scalars(select(AlteracaoItemComanda).where(AlteracaoItemComanda.comanda_id == comanda.id)
        .order_by(AlteracaoItemComanda.registrado_em, AlteracaoItemComanda.id))
    return [AlteracaoItemOut.model_validate(r.resultado) for r in registros]
