"""Inclusão atômica, sob os mesmos locks e permissões do fechamento financeiro."""
from sqlalchemy import select
from app.models import InclusaoServicoComanda, ItemComanda, Servico, SituacaoFinanceiraEnum, RespostaInclusaoComanda
from app.schemas.comanda import ItemComandaResponse
from app.schemas.itens_comanda import InclusaoServicoOut
from app.services import financeiro as f
from app.services.financeiro_errors import EntradaFinanceiraInvalida, EstadoFinanceiroIncompativel, HistoricoFinanceiroNaoVerificado
from app.services.regras_financeiras import LIMITE, fingerprint, identificador, valor_monetario
from app.services.totais_comanda import resumo_totais


def adicionar_servico(comanda_id, servico_id, quantidade, chave_idempotencia, db, usuario, filial_id=None):
    identificador(servico_id)
    identificador(chave_idempotencia)
    if type(quantidade) is not int or not 1 <= quantidade <= 999:
        raise EntradaFinanceiraInvalida('Quantidade deve ser inteira entre 1 e 999')
    esperado = fingerprint('incluir_servico', servico_id=servico_id, quantidade=quantidade)
    with f._escrita(db):
        ator, agendamento, comanda = f._contexto(db, usuario, comanda_id, filial_id)
        if comanda.tipo == 'avulsa':
            raise EstadoFinanceiroIncompativel('Comanda avulsa não aceita serviços')
        registro = f._registro(db, InclusaoServicoComanda, comanda, chave_idempotencia=chave_idempotencia)
        if registro:
            f._repeticao(registro, esperado)
            original = db.get(RespostaInclusaoComanda, registro.id)
            if original is None:
                raise f.DadosFinanceirosInconsistentes('Resposta original da inclusão ausente')
            return InclusaoServicoOut.model_validate(original.resposta)
        else:
            resumo = f._resumo(db, comanda)
            if resumo.situacao == SituacaoFinanceiraEnum.NAO_VERIFICADO:
                raise HistoricoFinanceiroNaoVerificado('Comanda sem comprovação financeira')
            if resumo.situacao != SituacaoFinanceiraEnum.ABERTO or comanda.status != 'aberta' or agendamento.status == 'cancelado':
                raise EstadoFinanceiroIncompativel('Somente comandas abertas e verificadas aceitam serviços')
            # SHARE estabiliza atividade/preço do catálogo até o commit. Não
            # modifica duração, agendamento nem snapshots dos itens anteriores.
            servico = db.scalar(select(Servico).where(Servico.id == servico_id).with_for_update(read=True).execution_options(populate_existing=True))
            if servico is None or not servico.ativo:
                raise EntradaFinanceiraInvalida('Serviço cadastrado e ativo obrigatório')
            preco = valor_monetario(servico.preco, permitir_zero=True)
            item = ItemComanda(comanda_id=comanda.id, tipo='servico', servico_id=servico.id,
                               descricao=servico.nome, quantidade=quantidade, preco_unitario=preco)
            db.add(item)
            db.flush()
            itens = db.scalars(select(ItemComanda).where(ItemComanda.comanda_id == comanda.id,
                ItemComanda.ativo.is_(True)).execution_options(populate_existing=True)).all()
            total = resumo_totais(itens, comanda.desconto_tipo, comanda.desconto_valor)['total']
            if total > LIMITE:
                raise EntradaFinanceiraInvalida('Total excede o limite monetário')
            comanda.versao_itens += 1
            comanda.valor_total = total
            from app.services import comissoes
            comissoes.fixar(db, comanda, item, comanda.barbeiro_id)
            comissoes.registrar(db, comanda, resumo.recebido_liquido, 'inclusao', ator.id, chave_idempotencia)
            registro = InclusaoServicoComanda(comanda_id=comanda.id, filial_id=comanda.filial_id,
                item_id=item.id, registrado_por=ator.id, chave_idempotencia=chave_idempotencia,
                fingerprint=esperado, total_resultante=f._total(db, comanda))
            db.add(registro)
            db.flush()
            db.refresh(registro)
        # Materializar antes do único commit: nenhuma leitura posterior ao commit.
        resultado = InclusaoServicoOut(item=ItemComandaResponse.model_validate(item), total=registro.total_resultante,
            registrado_em=registro.registrado_em, registrado_por=registro.registrado_por,
            chave_idempotencia=registro.chave_idempotencia)
        db.add(RespostaInclusaoComanda(inclusao_id=registro.id, resposta=resultado.model_dump(mode='json')))
    return resultado
