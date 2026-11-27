"""Gestão ADMIN serializada pela filial, sem commits fora da fronteira comum.

Ordem: ator SHARE, empresa SHARE, filial UPDATE, alvo SHARE, vínculo UPDATE.
Operações de agenda mantêm SHARE na filial antes de gravar agendamento/comanda;
assim a guarda observa todas as escritas confirmadas após qualquer espera.
"""
from sqlalchemy import select, and_, or_
from sqlalchemy.exc import OperationalError

from app.models import Empresa, Filial, Usuario, UsuarioFilial, Agendamento, PerfilEnum
from app.services import filiais, sessoes_equipe
from app.services.errors import SemPermissao, RecursoNaoEncontrado, ConflitoGestaoFilial
from app.services.persistencia import transacao_escrita, recarregar_confirmado


def _filial_exclusiva(db, ator, filial_id):
    ator = filiais.usuario_atual(db, ator, bloquear=True)
    if ator.perfil != PerfilEnum.ADMIN:
        raise SemPermissao('Sem permissão')
    db.scalars(select(Empresa).order_by(Empresa.id).with_for_update(read=True).execution_options(populate_existing=True)).all()
    unidade = db.scalar(select(Filial).where(Filial.id == filial_id).with_for_update().execution_options(populate_existing=True))
    if unidade is None:
        raise RecursoNaoEncontrado('Filial não encontrada')
    return unidade


def _impedir_reservas_abertas(db, filial_id, usuario_id=None):
    from app.services.agendamento import agora_local
    agora = agora_local()
    periodo_aberto = or_(
        Agendamento.data > agora.date(),
        and_(Agendamento.data == agora.date(), Agendamento.hora_fim > agora.time().replace(tzinfo=None)),
    )
    query = select(Agendamento.id).where(
        Agendamento.filial_id == filial_id,
        or_(Agendamento.status == 'em_atendimento', and_(
            Agendamento.status.notin_(('cancelado', 'concluido', 'nao_compareceu')), periodo_aberto,
        )),
    )
    if usuario_id is not None:
        query = query.where(Agendamento.barbeiro_id == usuario_id)
    if db.scalar(query.limit(1)) is not None:
        raise ConflitoGestaoFilial('Há agendamentos futuros ativos ou atendimentos em andamento nesta filial')


def definir_vinculo(db, ator, filial_id, usuario_id, ativo):
    with transacao_escrita(db):
        filial = _filial_exclusiva(db, ator, filial_id)
        alvo = db.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update(read=True).execution_options(populate_existing=True))
        if alvo is None:
            raise RecursoNaoEncontrado('Usuário não encontrado')
        vinculo = db.scalar(select(UsuarioFilial).where(
            UsuarioFilial.usuario_id == usuario_id, UsuarioFilial.filial_id == filial_id,
        ).with_for_update().execution_options(populate_existing=True))
        mudou = vinculo is None or vinculo.ativo != ativo
        if ativo:
            if not filial.ativa or not filial.empresa.ativa or not alvo.ativo:
                raise ConflitoGestaoFilial('Filial, empresa e usuário precisam estar ativos')
            if vinculo is None:
                vinculo = UsuarioFilial(usuario_id=usuario_id, filial_id=filial_id, ativo=True)
                db.add(vinculo)
            elif not vinculo.ativo:
                vinculo.ativo = True
        else:
            if vinculo is None:
                raise RecursoNaoEncontrado('Vínculo não encontrado')
            # Verifica históricos mesmo se o perfil global foi alterado.
            _impedir_reservas_abertas(db, filial_id, usuario_id)
            if vinculo.ativo:
                vinculo.ativo = False
        if mudou and alvo.perfil == PerfilEnum.ADMIN:
            # Bloqueia novos logins antes de invalidar a confiança e os desafios.
            try:
                db.scalar(select(Usuario.id).where(Usuario.id == usuario_id).with_for_update(nowait=True))
            except OperationalError as exc:
                if (getattr(exc.orig, 'pgcode', None) or getattr(exc.orig, 'sqlstate', None)) == '55P03':
                    raise ConflitoGestaoFilial('Cadastro em uso. Aguarde e tente novamente') from exc
                raise
            sessoes_equipe.revogar_todas(db, alvo.id)
    recarregar_confirmado(db, vinculo)
    return vinculo


def desativar_filial(db, ator, filial_id):
    with transacao_escrita(db):
        filial = _filial_exclusiva(db, ator, filial_id)
        _impedir_reservas_abertas(db, filial_id)
        if filial.ativa:
            filial.ativa = False


def configurar_agenda_publica(db, ator, filial_id, dados):
    with transacao_escrita(db):
        filial = _filial_exclusiva(db, ator, filial_id)
        filial.endereco = dados.endereco or None
        filial.agenda_publica = dados.agenda_publica
    recarregar_confirmado(db, filial)
    return filial


def consultar_vinculos(db, ator, filial_id):
    ator = filiais.usuario_atual(db, ator)
    if ator.perfil != PerfilEnum.ADMIN:
        raise SemPermissao('Sem permissão')
    if db.get(Filial, filial_id) is None:
        raise RecursoNaoEncontrado('Filial não encontrada')
    return db.scalars(select(UsuarioFilial).where(UsuarioFilial.filial_id == filial_id).order_by(UsuarioFilial.usuario_id)).all()
