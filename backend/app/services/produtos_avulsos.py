"""Operações internas de estoque para comandas avulsas, sem endpoints públicos."""
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Comanda, ItemComanda, PerfilEnum, ProdutoEstoque
from app.models.alteracao_item import AlteracaoItemComanda
from app.models.comissao import ExcecaoComissao
from app.models.estoque import MovimentoEstoque
from app.models.financeiro import ControleFinanceiroComanda, PagamentoComanda, FechamentoFinanceiroComanda
from app.services import filiais
from app.services.errors import SemPermissao, FilialObrigatoria
from app.services.financeiro_errors import (
    EntradaFinanceiraInvalida, EstadoFinanceiroIncompativel, ComandaFinanceiraNaoEncontrada,
    AcessoFinanceiroNegado, ItensAposPagamento, ConflitoIdempotenciaFinanceira, VersaoItensDesatualizada,
)
from app.services.persistencia import transacao_escrita
from app.services.regras_financeiras import fingerprint, identificador, LIMITE
from app.services.totais_comanda import resumo_totais, subtotal_item


def abrir(db: Session, usuario, filial_id: UUID, chave: UUID):
    """Abre uma comanda com controle financeiro vazio em uma única transação."""
    identificador(filial_id); identificador(chave)
    with transacao_escrita(db):
        try:
            ator = filiais.usuario_atual(db, usuario, bloquear=True)
            if ator.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
                raise AcessoFinanceiroNegado('Somente gestão pode abrir comanda')
            filial = filiais.resolver_filial(db, ator, filial_id, bloquear=True)
        except SemPermissao as exc:
            raise AcessoFinanceiroNegado('Sem acesso à filial') from exc
        except FilialObrigatoria as exc:
            raise EntradaFinanceiraInvalida('Informe uma filial autorizada') from exc
        ident = uuid4()
        criado = db.execute(insert(Comanda).values(id=ident, filial_id=filial.id, tipo='avulsa',
            chave_abertura=chave, abertura_por=ator.id, status='aberta', data_abertura=func.now(),
            valor_total=0, comissoes_ativas=True).on_conflict_do_nothing(
                constraint='uq_comanda_abertura_filial').returning(Comanda.id)).scalar_one_or_none()
        if criado is None:
            existente = db.scalar(select(Comanda).where(Comanda.filial_id == filial.id, Comanda.chave_abertura == chave))
            if existente is None or existente.abertura_por != ator.id:
                raise ConflitoIdempotenciaFinanceira('Chave de abertura já utilizada')
            return {'id': str(existente.id), 'filial_id': str(filial.id), 'tipo': 'avulsa'}
        db.add(ControleFinanceiroComanda(comanda_id=criado, filial_id=filial.id,
            registrado_por=ator.id, motivo='Abertura de comanda avulsa'))
        db.flush()
        return {'id': str(criado), 'filial_id': str(filial.id), 'tipo': 'avulsa'}


def historico(db: Session, usuario, filial_id: UUID, comanda_id: UUID):
    from app.services import financeiro
    _, _, comanda = financeiro._contexto(db, usuario, comanda_id, filial_id, leitura=True)
    registros = db.scalars(select(AlteracaoItemComanda).where(
        AlteracaoItemComanda.comanda_id == comanda.id,
        AlteracaoItemComanda.filial_id == comanda.filial_id,
    ).order_by(AlteracaoItemComanda.registrado_em, AlteracaoItemComanda.id)).all()
    return [dict(r.resultado) for r in registros if 'produto_id' in r.resultado]


def alterar(db: Session, usuario, filial_id: UUID, comanda_id: UUID, chave: UUID, *, acao: str,
            quantidade: int | None = None, produto_id: UUID | None = None,
            item_id: UUID | None = None, profissional_id: UUID | None = None, versao: int | None = None):
    """Adiciona, altera quantidade ou remove; retorna a resposta original em repetição."""
    for valor in (filial_id, comanda_id, chave): identificador(valor)
    if acao not in ('adicionar', 'quantidade', 'remover'):
        raise EntradaFinanceiraInvalida('Operação inválida')
    if acao != 'remover' and (type(quantidade) is not int or not 1 <= quantidade <= 999):
        raise EntradaFinanceiraInvalida('Quantidade deve ser inteira entre 1 e 999')
    if acao == 'adicionar':
        identificador(produto_id)
        if item_id is not None: raise EntradaFinanceiraInvalida('Item inesperado')
        if profissional_id is not None: identificador(profissional_id)
    else:
        identificador(item_id)
        if produto_id is not None or profissional_id is not None or (acao == 'remover' and quantidade is not None):
            raise EntradaFinanceiraInvalida('Parâmetros incompatíveis')
    esperado = fingerprint('produto_avulso_v1', acao=acao, produto_id=produto_id, item_id=item_id,
                           quantidade=quantidade, profissional_id=profissional_id,
                           **({'versao': versao} if versao is not None else {}))
    with transacao_escrita(db):
        try:
            ator = filiais.usuario_atual(db, usuario, bloquear=True)
            if ator.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
                raise AcessoFinanceiroNegado('Somente gestão pode alterar produtos')
            filial = filiais.resolver_filial(db, ator, filial_id, bloquear=True)
        except SemPermissao as exc:
            raise AcessoFinanceiroNegado('Sem acesso à filial') from exc
        except FilialObrigatoria as exc:
            raise EntradaFinanceiraInvalida('Informe uma filial autorizada') from exc
        from app.services import financeiro as financeiro
        ator, agendamento, comanda = financeiro._contexto(db, ator, comanda_id, filial.id)
        anterior = db.scalar(select(AlteracaoItemComanda).where(AlteracaoItemComanda.comanda_id == comanda.id, AlteracaoItemComanda.chave_idempotencia == chave))
        if anterior is not None:
            if anterior.fingerprint != esperado: raise ConflitoIdempotenciaFinanceira('Chave já utilizada com outros dados')
            return anterior.resultado
        if versao is not None and comanda.versao_itens != versao:
            raise VersaoItensDesatualizada('Atualize os itens da comanda antes de alterar')
        if comanda.status != 'aberta' or comanda.data_fechamento is not None:
            raise EstadoFinanceiroIncompativel('Comanda não está aberta')
        if agendamento is not None:
            if agendamento.status == 'cancelado' or financeiro._resumo(db, comanda).situacao != 'aberto':
                raise EstadoFinanceiroIncompativel('Somente comandas abertas e financeiramente verificadas aceitam produtos')
        # Até a integração financeira existir, não ajustar itens que tenham histórico financeiro.
        if db.scalar(select(PagamentoComanda.id).where(PagamentoComanda.comanda_id == comanda.id).limit(1)) or db.get(FechamentoFinanceiroComanda, comanda.id):
            raise ItensAposPagamento('Itens não podem ser alterados após um pagamento')
        item = None if acao == 'adicionar' else db.scalar(select(ItemComanda).where(ItemComanda.id == item_id, ItemComanda.comanda_id == comanda.id).with_for_update())
        if acao != 'adicionar' and (item is None or not item.ativo or item.tipo != 'produto'):
            raise EstadoFinanceiroIncompativel('Item ativo não encontrado')
        produto = db.scalar(select(ProdutoEstoque).where(ProdutoEstoque.id == (produto_id if item is None else item.produto_id), ProdutoEstoque.filial_id == filial.id).with_for_update().execution_options(populate_existing=True))
        if produto is None: raise ComandaFinanceiraNaoEncontrada('Produto não encontrado nesta filial')
        if acao == 'adicionar':
            if not produto.ativo or not produto.venda or produto.preco_venda is None: raise EntradaFinanceiraInvalida('Produto indisponível para venda')
            percentual = produto.comissao_padrao
            if profissional_id:
                filiais.validar_profissional(db, profissional_id, filial.id)
                regra = db.scalar(select(ExcecaoComissao).where(ExcecaoComissao.filial_id == filial.id, ExcecaoComissao.profissional_id == profissional_id, ExcecaoComissao.produto_id == produto.id, ExcecaoComissao.ativo.is_(True)).with_for_update(read=True))
                if regra: percentual = regra.percentual
            item = ItemComanda(id=uuid4(), comanda_id=comanda.id, comanda_tipo=comanda.tipo, filial_id=filial.id, produto_id=produto.id, tipo='produto', descricao=produto.nome, quantidade=quantidade, preco_unitario=produto.preco_venda, custo_snapshot=produto.custo, comissao_percentual_snapshot=percentual, comissao_profissional_id=profissional_id)
            db.add(item)
            delta = -quantidade
        else:
            delta = item.quantidade if acao == 'remover' else item.quantidade - quantidade
            if delta == 0: raise EntradaFinanceiraInvalida('Quantidade não foi alterada')
            if delta < 0 and (not produto.ativo or not produto.venda): raise EntradaFinanceiraInvalida('Produto indisponível para venda')
            if acao == 'remover': item.ativo = False
            else: item.quantidade = quantidade
            if acao != 'remover':
                try: subtotal_item(item)
                except ValueError: raise EntradaFinanceiraInvalida('Desconto incompatível com a nova quantidade') from None
        saldo = produto.saldo + Decimal(delta)
        if saldo < 0: raise EstadoFinanceiroIncompativel('Estoque insuficiente')
        if saldo > Decimal('99999999999.999'): raise EstadoFinanceiroIncompativel('Saldo excede o limite')
        produto.saldo = saldo
        db.flush()
        itens = db.scalars(select(ItemComanda).where(ItemComanda.comanda_id == comanda.id, ItemComanda.ativo.is_(True))).all()
        try: total = resumo_totais(itens, comanda.desconto_tipo, comanda.desconto_valor)['total']
        except ValueError: raise EntradaFinanceiraInvalida('Desconto incompatível com o novo total') from None
        if total > LIMITE: raise EntradaFinanceiraInvalida('Total excede o limite')
        comanda.valor_total = total
        comanda.versao_itens += 1
        from app.services import comissoes
        if acao == 'adicionar': comissoes.fixar(db, comanda, item, profissional_id)
        comissoes.registrar(db, comanda, Decimal('0'), 'produto_avulso', ator.id, chave)
        resultado = {'item_id': str(item.id), 'produto_id': str(produto.id), 'acao': acao, 'quantidade': item.quantidade, 'ativo': item.ativo, 'saldo': str(saldo), 'total': str(total), 'versao': comanda.versao_itens}
        db.add(MovimentoEstoque(produto_id=produto.id, filial_id=filial.id, comanda_id=comanda.id, item_comanda_id=item.id, tipo='baixa' if delta < 0 else 'entrada', quantidade=delta, saldo_apos=saldo, motivo='Operação de produto em comanda avulsa', registrado_por=ator.id, chave_idempotencia=chave))
        registro = AlteracaoItemComanda(comanda_id=comanda.id, filial_id=filial.id, item_id=item.id, registrado_por=ator.id, motivo='Operação de produto em comanda avulsa', chave_idempotencia=chave, fingerprint=esperado, resultado=resultado)
        db.add(registro)
        db.flush()
        db.refresh(registro)
        resultado = registro.resultado
    return resultado
