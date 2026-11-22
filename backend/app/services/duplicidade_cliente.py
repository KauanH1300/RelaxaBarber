"""Associações internas. Nenhuma operação do portal resolve estes aliases."""
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import aliased

from app.models import Cliente, ClienteFilial, ContaPortalCliente, DecisaoCliente, ParCliente, PerfilEnum
from app.schemas.duplicidade_cliente import RevisaoClienteOut, RevisaoClienteLista
from app.services import filiais
from app.services.errors import ConflitoEstadoAgendamento, RecursoNaoEncontrado, SemPermissao
from app.services.persistencia import transacao_escrita
from app.services.regras_financeiras import fingerprint


class RevisaoIncompativel(ValueError):
    pass


def _travar(db, *, exclusiva=False):
    if db.get_bind().dialect.name == 'postgresql':
        # Gate comum às decisões, novas reservas internas e vendas identificadas.
        funcao = 'pg_advisory_xact_lock' if exclusiva else 'pg_advisory_xact_lock_shared'
        db.execute(text(f'SELECT pg_catalog.{funcao}(728413920, 2)'))


def _vinculo(cliente_id, filial_id):
    v = aliased(ClienteFilial)
    return select(v.id).where(v.cliente_id == cliente_id, v.filial_id == filial_id).correlate_except(v).exists()


def par_resolvido(a, b):
    par = aliased(ParCliente)
    return select(par.cliente_a).where(
        par.estado.in_(('associado', 'diferentes')),
        or_(and_(par.cliente_a == a, par.cliente_b == b),
            and_(par.cliente_a == b, par.cliente_b == a)),
    ).correlate_except(par).exists()


def _filiais(db, cliente_id):
    return set(db.scalars(select(ClienteFilial.filial_id).where(ClienteFilial.cliente_id == cliente_id)))


def _principal_de(associado_id):
    return select(ParCliente.principal_id).where(ParCliente.associado_id == associado_id)


def visivel_no_seletor(cliente_id, filiais_visiveis=None):
    criterio = ~_principal_de(cliente_id).exists()
    if filiais_visiveis is None:
        return criterio
    vinculo = select(ClienteFilial.id).where(
        ClienteFilial.cliente_id == cliente_id, ClienteFilial.filial_id.in_(filiais_visiveis),
    ).correlate(Cliente).exists()
    principal = select(ParCliente.cliente_a).where(ParCliente.principal_id == cliente_id).exists()
    return criterio & (~principal | vinculo)


def cliente_para_nova_operacao(db, cliente_id, filial_id, *, exigir_vinculo=False):
    _travar(db)
    principal = db.scalar(_principal_de(cliente_id))
    raiz = principal or cliente_id
    participa = principal is not None or db.scalar(select(ParCliente.principal_id)
                                                    .where(ParCliente.principal_id == raiz).limit(1)) is not None
    if exigir_vinculo or participa:
        ids_locais = set(db.scalars(select(ClienteFilial.cliente_id).where(
            ClienteFilial.filial_id == filial_id, ClienteFilial.cliente_id.in_([cliente_id, raiz]),
        )))
        if not {cliente_id, raiz}.issubset(ids_locais):
            raise RecursoNaoEncontrado('Cadastro indisponível nesta filial. Selecione um cliente autorizado.')
    return raiz


def proteger_desativacao(db, cliente_id):
    _travar(db, exclusiva=True)
    if db.scalar(select(ParCliente.associado_id).where(ParCliente.principal_id == cliente_id).limit(1)):
        raise RevisaoIncompativel('Desfaça as associações antes de desativar a ficha principal.')


def busca_por_associado(criterio, filiais_visiveis):
    associado = aliased(Cliente)
    v = aliased(ClienteFilial)
    par = aliased(ParCliente)
    return select(par.associado_id).join(associado, associado.id == par.associado_id).join(
        v, v.cliente_id == associado.id,
    ).where(par.principal_id == Cliente.id, v.filial_id.in_(filiais_visiveis),
            criterio(associado)).correlate(Cliente).exists()


def filtro_historico(cliente_coluna, filial_coluna, principal_id):
    par = aliased(ParCliente)
    associado = select(par.associado_id).where(
        par.principal_id == principal_id, par.associado_id == cliente_coluna,
        _vinculo(par.associado_id, filial_coluna), _vinculo(principal_id, filial_coluna),
    ).correlate_except(par).exists()
    return or_(cliente_coluna == principal_id, associado)


def _par(a, b):
    return tuple(sorted((a, b)))


def _saida(par, *, historico=False):
    return RevisaoClienteOut(cliente_a=par.cliente_a, cliente_b=par.cliente_b,
                             estado=par.estado, versao=par.chave if historico else par.versao,
                             principal_id=par.principal_id)


def listar(db, filial_id):
    a, b = aliased(Cliente), aliased(Cliente)
    linhas = db.execute(select(ParCliente, a.nome, b.nome)
        .join(a, a.id == ParCliente.cliente_a).join(b, b.id == ParCliente.cliente_b)
        .where(_vinculo(a.id, filial_id), _vinculo(b.id, filial_id))
        .order_by(ParCliente.estado, a.nome, b.nome, ParCliente.cliente_a, ParCliente.cliente_b))
    return [RevisaoClienteLista(**_saida(par).model_dump(), nome_a=nome_a, nome_b=nome_b)
            for par, nome_a, nome_b in linhas]


def _escolher_principal(db, clientes, ids):
    a, b = ids
    contas = set(db.scalars(select(ContaPortalCliente.cliente_id).where(
        ContaPortalCliente.cliente_id.in_(ids),
    )))
    contas = {id_ for id_ in contas if clientes[id_].conta_ativada and clientes[id_].senha_hash}
    if len(contas) == 2:
        raise RevisaoIncompativel('Duas contas com login ativo exigem análise fora da associação simples.')
    principais = set(db.scalars(select(ParCliente.principal_id).where(ParCliente.principal_id.in_(ids))))
    if any(db.scalars(select(ParCliente.associado_id).where(ParCliente.associado_id.in_(ids)))) or len(principais) > 1:
        raise RevisaoIncompativel('A associação causaria um ciclo ou uniria conjuntos existentes.')
    principal = next(iter(contas or principais), a)
    if principais and principal not in principais:
        raise RevisaoIncompativel('Desfaça as associações existentes antes de alterar a ficha principal.')
    associado = b if principal == a else a
    if not _filiais(db, associado).issubset(_filiais(db, principal)):
        if not contas and not principais and _filiais(db, principal).issubset(_filiais(db, associado)):
            principal, associado = associado, principal
        else:
            raise RevisaoIncompativel('A ficha principal precisa estar vinculada às filiais do cadastro associado.')
    membros = [principal, *db.scalars(select(ParCliente.associado_id).where(
        ParCliente.principal_id == principal,
    ))]
    if db.scalar(select(ParCliente.cliente_a).where(
        ParCliente.estado == 'diferentes',
        or_(and_(ParCliente.cliente_a.in_(membros), ParCliente.cliente_b == associado),
            and_(ParCliente.cliente_b.in_(membros), ParCliente.cliente_a == associado)),
    ).limit(1)):
        raise RevisaoIncompativel('Há uma decisão de pessoas diferentes neste conjunto. Reabra o par antes.')
    return principal, associado


def decidir(db, usuario, filial_id, dados):
    with transacao_escrita(db):
        ator = filiais.usuario_atual(db, usuario, bloquear=True)
        if ator.perfil not in (PerfilEnum.ADMIN, PerfilEnum.RECEPCAO) or (
            dados.acao != 'encaminhar' and ator.perfil != PerfilEnum.ADMIN
        ):
            raise SemPermissao('Somente ADMIN pode decidir, reabrir ou desfazer associações.')
        filial = filiais.resolver_filial(db, ator, filial_id, bloquear=True)
        a, b = _par(dados.cliente_a, dados.cliente_b)
        if a == b:
            raise RevisaoIncompativel('Selecione dois cadastros distintos.')
        _travar(db, exclusiva=True)
        clientes = {c.id: c for c in db.scalars(select(Cliente).where(
            Cliente.id.in_([a, b]), _vinculo(Cliente.id, filial.id),
        ).order_by(Cliente.id).with_for_update(of=Cliente).execution_options(populate_existing=True))}
        if len(clientes) != 2:
            raise RecursoNaoEncontrado('Par de clientes não encontrado nesta filial.')
        marca = fingerprint('revisao_cliente', filial=filial.id, ator=ator.id, a=a, b=b,
                           **dados.model_dump(exclude={'chave', 'cliente_a', 'cliente_b'}))
        anterior = db.get(DecisaoCliente, dados.chave)
        if anterior:
            if anterior.fingerprint != marca:
                raise ConflitoEstadoAgendamento('Chave da decisão já usada com outros dados.')
            return _saida(anterior, historico=True)
        par = db.get(ParCliente, (a, b))
        if dados.versao != (par.versao if par else None):
            raise ConflitoEstadoAgendamento('A análise mudou. Atualize antes de continuar.')
        atual = par.estado if par else 'pendente'
        principal = associado = None
        if dados.acao in ('encaminhar', 'associar', 'diferentes'):
            if atual not in ('pendente', 'encaminhado', 'reaberto'):
                raise RevisaoIncompativel('Este par já tem decisão definitiva.')
            if dados.acao == 'encaminhar' and atual == 'encaminhado':
                raise RevisaoIncompativel('Este par já está encaminhado.')
            if not clientes[a].ativo or not clientes[b].ativo or not clientes[a].telefone_normalizado or (
                clientes[a].telefone_normalizado != clientes[b].telefone_normalizado
            ):
                raise RevisaoIncompativel('O par deixou de ser um candidato ativo por telefone.')
            if dados.acao != 'encaminhar':
                if not dados.identidade_confirmada or not dados.metodo:
                    raise RevisaoIncompativel('Confirme a conferência de identidade e informe o método utilizado.')
                if dados.acao == 'associar':
                    principal, associado = _escolher_principal(db, clientes, (a, b))
                else:
                    raiz_a, raiz_b = (db.scalar(_principal_de(id_)) or id_ for id_ in (a, b))
                    if raiz_a == raiz_b:
                        raise RevisaoIncompativel('Desfaça a associação antes de marcar pessoas diferentes.')
            estado = {'encaminhar':'encaminhado', 'associar':'associado', 'diferentes':'diferentes'}[dados.acao]
        else:
            exigido = 'diferentes' if dados.acao == 'reabrir' else 'associado'
            if atual != exigido:
                raise RevisaoIncompativel('O estado atual do par não permite esta ação.')
            estado = 'reaberto'
        if par is None:
            par = ParCliente(cliente_a=a, cliente_b=b)
            db.add(par)
        par.estado, par.filial_id, par.versao = estado, filial.id, dados.chave
        par.principal_id, par.associado_id = principal, associado
        db.add(DecisaoCliente(chave=dados.chave, cliente_a=a, cliente_b=b, filial_id=filial.id,
                              ator_id=ator.id, acao=dados.acao, estado_anterior=atual, estado=estado,
                              principal_id=principal, metodo=dados.metodo, justificativa=dados.justificativa,
                              fingerprint=marca))
        db.flush()
        return _saida(par)
