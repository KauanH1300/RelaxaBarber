import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError


@pytest.mark.parametrize('operation', ['cliente_create', 'cliente_update', 'cliente_delete', 'servico_create', 'servico_update', 'servico_delete', 'usuario_create'])
def test_escritas_relacionadas_rollback(operation, isolated_runtime, monkeypatch):
    from app.services.persistencia import FalhaPersistencia
    from app.schemas.cliente import ClienteCreate, ClienteUpdate
    from app.schemas.servico import ServicoCreate, ServicoUpdate
    from app.schemas.usuario import UsuarioCreate
    db = MagicMock()
    db.commit.side_effect = IntegrityError('SQL interno', {}, Exception('mensagem privada'))
    user = SimpleNamespace(id=uuid4(), perfil='admin')
    target = SimpleNamespace(id=uuid4(), nome='Anterior', ativo=True)
    db.query.return_value.filter.return_value.first.return_value = target
    db.scalar.return_value = None
    clients = importlib.import_module('app.api.routes.clientes')
    services = importlib.import_module('app.api.routes.servico')
    users = importlib.import_module('app.api.routes.usuarios')
    monkeypatch.setattr(users, 'hash_senha', lambda password: 'hash-exclusivo-do-teste')
    with pytest.raises(FalhaPersistencia):
        if operation == 'cliente_create':
            db.query.return_value.filter.return_value.first.return_value = None
            clients.criar_cliente(ClienteCreate(nome='Teste', telefone='81999999999'), db)
        elif operation == 'cliente_update':
            clients.editar_cliente(target.id, ClienteUpdate(nome='Novo'), db)
        elif operation == 'cliente_delete':
            clients.desativar_cliente(target.id, db, user)
        elif operation == 'servico_create':
            services.criar_servico(ServicoCreate(nome='Corte', preco=0, tempo_estimado=30, comissao_padrao=10), db, user)
        elif operation == 'servico_update':
            services.atualizar_servico(target.id, ServicoUpdate(nome='Novo'), db, user)
        elif operation == 'servico_delete':
            services.excluir_servico(target.id, db, user)
        else:
            users.criar_usuario(UsuarioCreate(nome='Teste', email='teste@example.com', senha='senha-ficticia', perfil='barbeiro'), db, user)
    db.commit.assert_called_once()
    db.rollback.assert_called_once()
    db.refresh.assert_not_called()
