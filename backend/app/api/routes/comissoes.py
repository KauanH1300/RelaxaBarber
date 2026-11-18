from datetime import datetime
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.models import PerfilEnum, Servico, Usuario
from app.models.comissao import ExcecaoComissao
from app.models.estoque import ProdutoEstoque
from app.schemas.valores import Comissao
from app.services import filiais
from app.services.errors import SemPermissao, FilialObrigatoria, RecursoNaoEncontrado
from app.services.persistencia import transacao_escrita, recarregar_confirmado

router=APIRouter(prefix='/comissoes',tags=['Comissões'])

class ExcecaoDados(BaseModel):
    servico_id: UUID | None = None
    produto_id: UUID | None = None
    percentual: Comissao
    ativo: bool = True
    @model_validator(mode='after')
    def validar_item(self):
        if (self.servico_id is None) == (self.produto_id is None):
            raise ValueError('Informe exatamente um serviço ou produto')
        return self

class ExcecaoOut(ExcecaoDados):
    model_config=ConfigDict(from_attributes=True)
    id: UUID
    filial_id: UUID
    profissional_id: UUID
    atualizado_por: UUID
    atualizado_em: datetime


def contexto(db, usuario, filial_id, profissional_id, escrita):
    try:
        usuario=filiais.usuario_atual(db,usuario,bloquear=escrita)
        if usuario.perfil != PerfilEnum.ADMIN: raise SemPermissao('Somente administrador pode gerenciar comissões')
        filial=filiais.resolver_filial(db,usuario,filial_id,bloquear=escrita)
        if escrita:
            db.scalar(select(Usuario).where(Usuario.id==profissional_id).with_for_update())
        filiais.validar_profissional(db,profissional_id,filial.id)
        return usuario,filial
    except SemPermissao as exc: raise HTTPException(403,str(exc)) from exc
    except FilialObrigatoria as exc: raise HTTPException(422,str(exc)) from exc
    except RecursoNaoEncontrado as exc: raise HTTPException(404,str(exc)) from exc

@router.get('/profissionais/{profissional_id}', response_model=list[ExcecaoOut])
def listar(profissional_id: UUID, filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    _,filial=contexto(db,usuario,filial_id,profissional_id,False)
    return db.scalars(select(ExcecaoComissao).where(ExcecaoComissao.filial_id==filial.id,ExcecaoComissao.profissional_id==profissional_id).order_by(ExcecaoComissao.id)).all()

@router.put('/profissionais/{profissional_id}', response_model=ExcecaoOut)
def definir(profissional_id: UUID, dados: ExcecaoDados, filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    with transacao_escrita(db):
        usuario,filial=contexto(db,usuario,filial_id,profissional_id,True)
        if dados.servico_id:
            servico=db.scalar(select(Servico).where(Servico.id==dados.servico_id,Servico.ativo.is_(True)).with_for_update(read=True))
            if not servico: raise HTTPException(404,'Serviço ativo não encontrado')
        else:
            produto=db.scalar(select(ProdutoEstoque).where(ProdutoEstoque.id==dados.produto_id,ProdutoEstoque.filial_id==filial.id,ProdutoEstoque.venda.is_(True),ProdutoEstoque.ativo.is_(True)).with_for_update(read=True))
            if not produto: raise HTTPException(404,'Produto vendável não encontrado')
        registro=db.scalar(select(ExcecaoComissao).where(ExcecaoComissao.filial_id==filial.id,ExcecaoComissao.profissional_id==profissional_id,ExcecaoComissao.servico_id==dados.servico_id,ExcecaoComissao.produto_id==dados.produto_id).with_for_update())
        if registro is None:
            registro=ExcecaoComissao(filial_id=filial.id,profissional_id=profissional_id,atualizado_por=usuario.id,**dados.model_dump())
            db.add(registro)
        else:
            registro.percentual=dados.percentual;registro.ativo=dados.ativo;registro.atualizado_por=usuario.id
        db.flush()
    recarregar_confirmado(db,registro)
    return registro

class EventoOut(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID
    ordem: int
    item_id: UUID
    comanda_id: UUID
    filial_id: UUID
    profissional_id: UUID
    servico_id: UUID
    percentual: Comissao
    origem_percentual: str
    base: Decimal
    gerada: Decimal
    liberada: Decimal
    paga: Decimal
    operacao: str
    chave_operacao: UUID | None
    registrado_por: UUID | None
    registrado_em: datetime

@router.get('/comandas/{comanda_id}/historico', response_model=list[EventoOut])
def historico_comanda(comanda_id: UUID, filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    from app.services import financeiro
    from app.models.comissao import EventoComissao
    from app.services.financeiro_errors import AcessoFinanceiroNegado, ComandaFinanceiraNaoEncontrada
    try:
        ator,_,comanda=financeiro._contexto(db,usuario,comanda_id,filial_id,leitura=True)
        if ator.perfil == PerfilEnum.RECEPCAO: raise HTTPException(403,'Sem permissão para consultar comissões')
    except AcessoFinanceiroNegado as exc: raise HTTPException(403,str(exc)) from exc
    except ComandaFinanceiraNaoEncontrada as exc: raise HTTPException(404,str(exc)) from exc
    return db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==comanda.id,EventoComissao.filial_id==comanda.filial_id).order_by(EventoComissao.ordem)).all()

class ResumoComissoes(BaseModel):
    verificado: bool
    itens: list[EventoOut]
    gerada: Decimal
    liberada: Decimal
    paga: Decimal

@router.get('/comandas/{comanda_id}', response_model=ResumoComissoes)
def resumo_comanda(comanda_id: UUID, filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    from app.services import financeiro
    from app.models.comissao import EventoComissao
    from app.services.financeiro_errors import AcessoFinanceiroNegado, ComandaFinanceiraNaoEncontrada
    try:
        ator,_,comanda=financeiro._contexto(db,usuario,comanda_id,filial_id,leitura=True)
        if ator.perfil == PerfilEnum.RECEPCAO: raise HTTPException(403,'Sem permissão para consultar comissões')
    except AcessoFinanceiroNegado as exc: raise HTTPException(403,str(exc)) from exc
    except ComandaFinanceiraNaoEncontrada as exc: raise HTTPException(404,str(exc)) from exc
    eventos=db.scalars(select(EventoComissao).where(EventoComissao.comanda_id==comanda.id,EventoComissao.filial_id==comanda.filial_id).order_by(EventoComissao.ordem)).all()
    atuais={evento.item_id:evento for evento in eventos}
    itens=list(atuais.values())
    return ResumoComissoes(verificado=comanda.comissoes_ativas,itens=itens,
        gerada=sum((e.gerada for e in itens),Decimal('0.00')),
        liberada=sum((e.liberada for e in itens),Decimal('0.00')),
        paga=sum((e.paga for e in itens),Decimal('0.00')))
