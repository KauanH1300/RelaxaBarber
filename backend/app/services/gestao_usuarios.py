from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.models import Usuario, PerfilEnum, Empresa, Filial, Comanda
from app.models.usuario import PERFIS_PROFISSIONAIS
from app.services import filiais, recuperacao_equipe, sessoes_equipe
from app.services.errors import SemPermissao, RecursoNaoEncontrado, ConflitoGestaoFilial
from app.services.gestao_filiais import _impedir_reservas_abertas
from app.services.persistencia import transacao_escrita, recarregar_confirmado


def atualizar(db, ator, usuario_id, dados):
    with transacao_escrita(db):
        # NOWAIT avoids cycles with agenda's shared user/branch locks. Serializing
        # administrative edits also protects the last active administrator.
        try:
            usuarios = db.scalars(select(Usuario).order_by(Usuario.id).with_for_update(
                nowait=True).execution_options(populate_existing=True)).all()
            atual = filiais.usuario_atual(db, ator)
            if atual.perfil != PerfilEnum.ADMIN:
                raise SemPermissao('Somente administradores podem gerenciar funcionários')
            alvo = next((u for u in usuarios if u.id == usuario_id), None)
            if alvo is None:
                raise RecursoNaoEncontrado('Funcionário não encontrado')
            if alvo.id == atual.id and (not dados.ativo or dados.perfil != PerfilEnum.ADMIN):
                raise ConflitoGestaoFilial('Não é permitido inativar ou remover o próprio perfil de administrador')
            if alvo.ativo and alvo.perfil == PerfilEnum.ADMIN and (not dados.ativo or dados.perfil != PerfilEnum.ADMIN):
                if not any(u.id != alvo.id and u.ativo and u.perfil == PerfilEnum.ADMIN for u in usuarios):
                    raise ConflitoGestaoFilial('É necessário manter um administrador ativo')
            email = str(dados.email).lower()
            if any(u.id != alvo.id and u.email.lower() == email for u in usuarios):
                raise ConflitoGestaoFilial('E-mail já cadastrado')
            restringindo = (alvo.ativo and not dados.ativo) or (
                alvo.perfil in PERFIS_PROFISSIONAIS and dados.perfil not in PERFIS_PROFISSIONAIS)
            if restringindo:
                db.scalars(select(Empresa).order_by(Empresa.id).with_for_update(read=True, nowait=True)).all()
                unidades = db.scalars(select(Filial).order_by(Filial.id).with_for_update(nowait=True)).all()
                for unidade in unidades:
                    _impedir_reservas_abertas(db, unidade.id, alvo.id)
                if db.scalar(select(Comanda.id).where(Comanda.barbeiro_id == alvo.id, Comanda.status == 'aberta').limit(1)):
                    raise ConflitoGestaoFilial('Finalize as comandas abertas antes de inativar ou alterar o perfil profissional')
            alvo.nome = dados.nome
            if alvo.email != email:
                alvo.email_confirmado_em = None
                recuperacao_equipe.invalidar_codigos(db, alvo.id)
                recuperacao_equipe.invalidar_codigos(db, alvo.id, 'confirmacao')
                sessoes_equipe.revogar_todas(db, alvo.id)
            alvo.email = email
            alvo.telefone = dados.telefone
            alvo.perfil = dados.perfil
            alvo.ativo = dados.ativo
        except OperationalError as exc:
            code = getattr(exc.orig, 'pgcode', None) or getattr(exc.orig, 'sqlstate', None)
            if code == '55P03':
                raise ConflitoGestaoFilial('Cadastro em uso. Aguarde a operação em andamento e tente novamente') from exc
            raise
    recarregar_confirmado(db, alvo)
    return alvo
