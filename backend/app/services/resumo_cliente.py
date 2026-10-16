"""Leitura agregada sem escritas e sem inferir pagamentos.

filial_id valida o contexto de abertura do perfil, não restringe o consolidado:
ADMIN vê a empresa (inclusive histórico inativo); demais veem unidades ativas
hoje autorizadas e o mesmo escopo profissional permitido na agenda.
"""
from sqlalchemy import select, func, or_

from app.models import Agendamento, Cliente, ClienteFilial, Empresa, Filial, PerfilEnum
from app.services import filiais
from app.services.errors import RecursoNaoEncontrado, SemPermissao
from app.services.permissoes_agendamento import escopo_consulta
from app.schemas.resumo_cliente import ResumoCliente, ResumoFinanceiroCliente


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
    rows = db.execute(unidades.order_by(Filial.nome, Filial.id)).all()
    resultado = dict(
        cliente_id=cliente_id, escopo_filiais='empresa' if admin else 'filiais_autorizadas',
        escopo_profissional='proprio' if profissional_id is not None else 'todos',
        parcial=not admin, atendimentos_concluidos=sum(row[2] for row in rows),
        filiais=[dict(filial_id=ident, filial_nome=nome, atendimentos_concluidos=n) for ident, nome, n in rows],
    )
    return (ResumoFinanceiroCliente if financeiro else ResumoCliente)(**resultado)
