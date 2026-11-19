"""Snapshots e estados de comissão; chamador mantém lock da comanda até o commit."""
from decimal import Decimal
from sqlalchemy import select
from app.models import Servico, ItemComanda, Usuario
from app.models.comissao import ComissaoItem, EventoComissao, ExcecaoComissao
from app.services.comissoes_calculo import calcular

ZERO=Decimal('0.00')


def fixar(db, comanda, item, profissional_id):
    if not comanda.comissoes_ativas:
        return
    if item.tipo == 'produto' and item.produto_id is not None:
        if profissional_id is None: return
        if db.get(ComissaoItem, item.id) is not None: return
        regra=db.scalar(select(ExcecaoComissao).where(ExcecaoComissao.filial_id==comanda.filial_id,
            ExcecaoComissao.profissional_id==profissional_id,ExcecaoComissao.produto_id==item.produto_id,
            ExcecaoComissao.ativo.is_(True)).with_for_update(read=True).execution_options(populate_existing=True))
        db.add(ComissaoItem(item_id=item.id,comanda_id=comanda.id,filial_id=comanda.filial_id,
            profissional_id=profissional_id,produto_id=item.produto_id,percentual=item.comissao_percentual_snapshot,
            origem='excecao' if regra else 'padrao'))
        db.flush()
        return
    if item.tipo != 'servico' or item.servico_id is None:
        return
    # Locks partilhados estabilizam o catálogo e a configuração ao gravar o snapshot.
    servico=db.scalar(select(Servico).where(Servico.id==item.servico_id).with_for_update(read=True).execution_options(populate_existing=True))
    if servico is None: raise ValueError('Serviço de comissão não encontrado')
    regra=db.scalar(select(ExcecaoComissao).where(ExcecaoComissao.filial_id==comanda.filial_id,
        ExcecaoComissao.profissional_id==profissional_id,ExcecaoComissao.servico_id==item.servico_id,
        ExcecaoComissao.ativo.is_(True)).with_for_update(read=True).execution_options(populate_existing=True))
    percentual=regra.percentual if regra else servico.comissao_padrao
    origem='excecao' if regra else 'padrao'
    atual=db.get(ComissaoItem,item.id)
    if atual is None:
        db.add(ComissaoItem(item_id=item.id,comanda_id=comanda.id,filial_id=comanda.filial_id,
            profissional_id=profissional_id,servico_id=item.servico_id,percentual=percentual,origem=origem))
    else:
        atual.profissional_id=profissional_id;atual.servico_id=item.servico_id
        atual.percentual=percentual;atual.origem=origem
    db.flush()


def registrar(db, comanda, recebido, operacao, ator=None, chave=None):
    if not comanda.comissoes_ativas: return
    db.flush()
    itens=db.scalars(select(ItemComanda).where(ItemComanda.comanda_id==comanda.id).execution_options(populate_existing=True)).all()
    snapshots=db.scalars(select(ComissaoItem).where(ComissaoItem.comanda_id==comanda.id,
        ComissaoItem.filial_id==comanda.filial_id).execution_options(populate_existing=True)).all()
    ativos=calcular(itens,comanda.desconto_tipo,comanda.desconto_valor,
                    {s.item_id:s.percentual for s in snapshots},recebido)
    calculados={v.item_id:v for v in ativos}
    for snapshot in snapshots:
        valor=calculados.get(snapshot.item_id) if comanda.status != 'cancelada' else None
        evento=EventoComissao(item_id=snapshot.item_id,comanda_id=comanda.id,filial_id=comanda.filial_id,
            profissional_id=snapshot.profissional_id,servico_id=snapshot.servico_id,produto_id=snapshot.produto_id,
            percentual=snapshot.percentual,origem_percentual=snapshot.origem,
            base=valor.base if valor else ZERO,gerada=valor.gerada if valor else ZERO,
            liberada=valor.liberada if valor else ZERO,paga=ZERO,operacao=operacao,registrado_por=ator,chave_operacao=chave)
        db.add(evento)
    db.flush()
