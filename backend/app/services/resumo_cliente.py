"""Leitura agregada sem escritas e sem inferir pagamentos.

O resumo operacional conserva o escopo da agenda. No financeiro, informar
filial_id limita os valores à filial; sem filial, ADMIN consolida os vínculos
da empresa ativa, inclusive o histórico de unidades inativas.
"""
from collections import defaultdict

from sqlalchemy import and_, literal, select, func, or_, union_all

from app.models import Agendamento, Cliente, ClienteFilial, Comanda, Empresa, Filial, PerfilEnum
from app.models.financeiro import PagamentoComanda, EstornoPagamento
from app.services import filiais
from app.services.errors import RecursoNaoEncontrado, SemPermissao
from app.services.permissoes_agendamento import escopo_consulta
from app.schemas.resumo_cliente import ResumoCliente, ResumoFinanceiroCliente
from app.services.totais_comanda import ZERO


def consultar_resumo(db, usuario, cliente_id, filial_id=None, *, financeiro=False):
    usuario = filiais.usuario_atual(db, usuario)
    profissional_id = escopo_consulta(usuario, None)
    admin = usuario.perfil == PerfilEnum.ADMIN
    if financeiro and not admin:
        raise SemPermissao('Consulta financeira restrita a ADMIN')
    if filial_id is not None:
        filiais.resolver_filial(db, usuario, filial_id)

    # EXISTS evita multiplicar o cadastro por vínculos. Não revela clientes de
    # outra unidade via UUID, mesmo que conhecidos pela pesquisa global.
    acesso = select(Cliente.id).where(Cliente.id == cliente_id)
    autorizadas = filiais.consulta_autorizadas(usuario).with_only_columns(Filial.id).order_by(None)
    if not admin:
        if not db.scalar(select(autorizadas.exists())):
            raise SemPermissao('Sem acesso a uma filial ativa')
        vinculo = select(ClienteFilial.id).where(
            ClienteFilial.cliente_id == Cliente.id,
            ClienteFilial.filial_id == filial_id if filial_id is not None else ClienteFilial.filial_id.in_(autorizadas),
        ).exists()
        acesso = acesso.where(vinculo)
    else:
        # Empresa desativada não concede acesso, nem mesmo a ADMIN.
        if not db.scalar(select(Empresa.id).where(Empresa.ativa.is_(True))):
            raise SemPermissao('Empresa sem acesso ativo')
    if financeiro:
        vinculos = select(ClienteFilial.id).join(Filial).join(Empresa).where(
            ClienteFilial.cliente_id == Cliente.id, Empresa.ativa.is_(True),
        )
        if filial_id is not None:
            vinculos = vinculos.where(ClienteFilial.filial_id == filial_id)
        acesso = acesso.where(vinculos.exists())
    if db.scalar(acesso) is None:
        raise RecursoNaoEncontrado('Cliente não encontrado')

    # Agendamento é a unidade de contagem. Nunca juntar serviços ou itens.
    contagens = select(
        Agendamento.filial_id.label('filial_id'),
        func.count(Agendamento.id).label('quantidade'),
    ).where(Agendamento.cliente_id == cliente_id, Agendamento.status == 'concluido')
    if not admin:
        contagens = contagens.where(Agendamento.filial_id.in_(autorizadas))
    if profissional_id is not None:
        contagens = contagens.where(Agendamento.barbeiro_id == profissional_id)
    contagens = contagens.group_by(Agendamento.filial_id).subquery()
    vinculo_cliente = select(ClienteFilial.id).where(
        ClienteFilial.cliente_id == cliente_id, ClienteFilial.filial_id == Filial.id,
    ).exists()
    unidades = select(
        Filial.id, Filial.nome, func.coalesce(contagens.c.quantidade, 0),
    ).join(Empresa).outerjoin(contagens, contagens.c.filial_id == Filial.id).where(
        Empresa.ativa.is_(True), or_(vinculo_cliente, contagens.c.filial_id.is_not(None)),
    )
    if not admin:
        unidades = unidades.where(Filial.id.in_(autorizadas))
    if financeiro:
        unidades = unidades.where(vinculo_cliente)
        if filial_id is not None:
            unidades = unidades.where(Filial.id == filial_id)
    rows = db.execute(unidades.order_by(Filial.nome, Filial.id)).all()
    escopo = 'filial' if financeiro and filial_id is not None else 'empresa'
    resultado = dict(
        cliente_id=cliente_id, escopo_filiais=escopo if admin else 'filiais_autorizadas',
        escopo_profissional='proprio' if profissional_id is not None else 'todos',
        parcial=not admin, atendimentos_concluidos=sum(row[2] for row in rows),
        filiais=[dict(filial_id=ident, filial_nome=nome, atendimentos_concluidos=n) for ident, nome, n in rows],
    )
    if not financeiro:
        return ResumoCliente(**resultado)

    movimentacoes = movimentacoes_financeiras(db, cliente_id, [row[0] for row in rows])
    totais = defaultdict(lambda: ZERO)
    for linha in movimentacoes:
        totais[linha['filial_id']] += linha['total_gasto']
    for filial in resultado['filiais']:
        filial['total_gasto'] = totais[filial['filial_id']]
    return ResumoFinanceiroCliente(
        **resultado, total_gasto=sum(totais.values(), ZERO), movimentacoes=movimentacoes,
    )


def movimentacoes_financeiras(db, cliente_id, filial_ids):
    comandas = select(Comanda.id, Comanda.filial_id, Comanda.tipo).where(
        Comanda.cliente_id == cliente_id, Comanda.filial_id.in_(filial_ids),
    ).cte()

    def contexto(registro):
        return and_(registro.comanda_id == comandas.c.id, registro.filial_id == comandas.c.filial_id)

    # Cada lançamento aparece uma vez, mesmo com vários itens ou estornos.
    movimentos = union_all(
        select(PagamentoComanda.comanda_id.label('comanda_id'), PagamentoComanda.filial_id.label('filial_id'),
               PagamentoComanda.recebido_em.label('data'), PagamentoComanda.valor.label('recebido'),
               literal(ZERO).label('estornado')).select_from(comandas).join(PagamentoComanda, contexto(PagamentoComanda)),
        select(EstornoPagamento.comanda_id, EstornoPagamento.filial_id, EstornoPagamento.efetivado_em,
               literal(ZERO), EstornoPagamento.valor).select_from(comandas).join(EstornoPagamento, contexto(EstornoPagamento)),
    ).subquery()
    ultima = func.max(movimentos.c.data).label('ultima_movimentacao_em')
    recebido = func.sum(movimentos.c.recebido)
    estornado = func.sum(movimentos.c.estornado)
    consulta = select(
        comandas.c.id.label('comanda_id'), comandas.c.filial_id, Filial.nome.label('filial_nome'), comandas.c.tipo,
        ultima, recebido.label('recebido'), estornado.label('estornado'), (recebido - estornado).label('total_gasto'),
    ).select_from(comandas).join(movimentos, contexto(movimentos.c)).join(Filial, Filial.id == comandas.c.filial_id)
    return [dict(linha) for linha in db.execute(consulta.group_by(
        comandas.c.id, comandas.c.filial_id, comandas.c.tipo, Filial.nome,
    ).order_by(ultima.desc(), comandas.c.id)).mappings()]
