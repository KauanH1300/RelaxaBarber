from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.models import PerfilEnum
from app.models.estoque import ProdutoEstoque, MovimentoEstoque
from app.schemas.valores import Comissao
from app.services import filiais
from app.services.errors import SemPermissao, FilialObrigatoria
from app.services.persistencia import transacao_escrita, recarregar_confirmado

router = APIRouter(prefix='/estoque', tags=['Estoque'])
Quantidade = Decimal

class ProdutoDados(BaseModel):
    nome: str = Field(min_length=1, max_length=150)
    unidade: str = Field(min_length=1, max_length=20)
    venda: bool
    consumo: bool
    custo: Decimal = Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    preco_venda: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)
    comissao_padrao: Comissao | None = None
    estoque_minimo: Decimal = Field(ge=0, max_digits=14, decimal_places=3, allow_inf_nan=False)
    ativo: bool = True
    @model_validator(mode='after')
    def validar(self):
        self.nome = self.nome.strip(); self.unidade = self.unidade.strip()
        if not self.nome or not self.unidade or not (self.venda or self.consumo):
            raise ValueError('Informe nome, unidade e pelo menos uma finalidade')
        if self.venda and self.preco_venda is None:
            raise ValueError('Informe o preço de venda')
        return self

class ProdutoOut(ProdutoDados):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filial_id: UUID
    saldo: Decimal

class MovimentoDados(BaseModel):
    tipo: Literal['entrada','baixa','ajuste']
    quantidade: Decimal = Field(max_digits=14, decimal_places=3, allow_inf_nan=False)
    motivo: str = Field(min_length=1, max_length=1000)
    @model_validator(mode='after')
    def validar(self):
        self.motivo = self.motivo.strip()
        if not self.motivo or not self.quantidade or (self.tipo != 'ajuste' and self.quantidade <= 0):
            raise ValueError('Informe quantidade válida e motivo')
        return self

class MovimentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    produto_id: UUID
    filial_id: UUID
    tipo: str
    quantidade: Decimal
    saldo_apos: Decimal
    motivo: str
    registrado_por: UUID
    registrado_em: datetime
    chave_idempotencia: UUID

def contexto(db, usuario, filial_id, *, escrita=False):
    try:
        usuario = filiais.usuario_atual(db, usuario, bloquear=escrita)
        if usuario.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO):
            raise SemPermissao('Sem permissão para estoque')
        filial = filiais.resolver_filial(db, usuario, filial_id, bloquear=escrita)
        return usuario, filial
    except SemPermissao as exc:
        raise HTTPException(403, str(exc)) from exc
    except FilialObrigatoria as exc:
        raise HTTPException(422, str(exc)) from exc

def produto(db, filial, id, bloquear=False):
    query = select(ProdutoEstoque).where(ProdutoEstoque.id == id, ProdutoEstoque.filial_id == filial.id).execution_options(populate_existing=True)
    if bloquear: query = query.with_for_update()
    item = db.scalar(query)
    if item is None: raise HTTPException(404, 'Produto não encontrado')
    return item

@router.get('/produtos', response_model=list[ProdutoOut])
def listar(filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    ator, filial = contexto(db, usuario, filial_id)
    produtos = db.scalars(select(ProdutoEstoque).where(ProdutoEstoque.filial_id == filial.id).order_by(ProdutoEstoque.nome, ProdutoEstoque.id)).all()
    if ator.perfil != PerfilEnum.ADMIN:
        return JSONResponse(jsonable_encoder([ProdutoOut.model_validate(p).model_dump(exclude={'comissao_padrao'}) for p in produtos]))
    return produtos

@router.post('/produtos', response_model=ProdutoOut, status_code=201)
def criar(dados: ProdutoDados, filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    with transacao_escrita(db):
        usuario, filial = contexto(db, usuario, filial_id, escrita=True)
        if usuario.perfil != PerfilEnum.ADMIN: raise HTTPException(403, 'Somente administrador pode cadastrar produtos')
        payload = dados.model_dump()
        if payload['comissao_padrao'] is None: payload['comissao_padrao'] = Decimal('0')
        item = ProdutoEstoque(filial_id=filial.id, **payload)
        db.add(item); db.flush()
    recarregar_confirmado(db, item)
    return item

@router.put('/produtos/{id}', response_model=ProdutoOut)
def atualizar(id: UUID, dados: ProdutoDados, filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    with transacao_escrita(db):
        usuario, filial = contexto(db, usuario, filial_id, escrita=True)
        if usuario.perfil != PerfilEnum.ADMIN: raise HTTPException(403, 'Somente administrador pode editar produtos')
        item = produto(db, filial, id, True)
        if item.unidade != dados.unidade and db.scalar(select(MovimentoEstoque.id).where(MovimentoEstoque.produto_id == id).limit(1)):
            raise HTTPException(409, 'Unidade não pode mudar após movimentação')
        payload = dados.model_dump()
        if payload['comissao_padrao'] is None: payload.pop('comissao_padrao')
        for campo, valor in payload.items(): setattr(item, campo, valor)
        db.flush()
    recarregar_confirmado(db, item)
    return item

@router.get('/produtos/{id}/movimentos', response_model=list[MovimentoOut])
def historico(id: UUID, filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    _, filial = contexto(db, usuario, filial_id); produto(db, filial, id)
    return db.scalars(select(MovimentoEstoque).where(MovimentoEstoque.produto_id == id, MovimentoEstoque.filial_id == filial.id).order_by(MovimentoEstoque.registrado_em.desc(), MovimentoEstoque.id.desc())).all()

@router.post('/produtos/{id}/movimentos', response_model=MovimentoOut)
def movimentar(id: UUID, dados: MovimentoDados, chave: UUID = Header(alias='Idempotency-Key'), filial_id: UUID | None = None, db: Session = Depends(get_db), usuario=Depends(get_current_user)):
    with transacao_escrita(db):
        usuario, filial = contexto(db, usuario, filial_id, escrita=True)
        item = produto(db, filial, id, True)
        anterior = db.scalar(select(MovimentoEstoque).where(MovimentoEstoque.produto_id == id, MovimentoEstoque.filial_id == filial.id, MovimentoEstoque.chave_idempotencia == chave))
        delta = -dados.quantidade if dados.tipo == 'baixa' else dados.quantidade
        if anterior:
            if (anterior.produto_id, anterior.tipo, anterior.quantidade, anterior.motivo) != (id, dados.tipo, delta, dados.motivo):
                raise HTTPException(409, 'Chave já utilizada com outros dados')
            resultado = anterior
        else:
            if not item.ativo: raise HTTPException(409, 'Produto inativo')
            if dados.tipo == 'baixa' and not item.consumo: raise HTTPException(409, 'Produto não permite consumo interno')
            saldo = item.saldo + delta
            if saldo < 0: raise HTTPException(409, 'Saldo insuficiente')
            if saldo > Decimal('99999999999.999'): raise HTTPException(409, 'Saldo excede o limite')
            item.saldo = saldo
            resultado = MovimentoEstoque(produto_id=id, filial_id=filial.id, tipo=dados.tipo, quantidade=delta, saldo_apos=saldo, motivo=dados.motivo, registrado_por=usuario.id, chave_idempotencia=chave)
            db.add(resultado); db.flush()
    recarregar_confirmado(db, resultado)
    return resultado
