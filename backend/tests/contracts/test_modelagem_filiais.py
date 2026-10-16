"""Contrato estrutural sem importar configuração ou conectar em banco externo."""
from sqlalchemy import UniqueConstraint


def test_cadastros_continuam_globais(models):
    for model in (models.Usuario, models.Cliente, models.Servico):
        assert 'filial_id' not in model.__table__.c
    assert 'perfil' not in models.UsuarioFilial.__table__.c
    assert 'saldo' not in models.ClienteFilial.__table__.c
    assert 'total' not in models.ClienteFilial.__table__.c
    assert not models.Agendamento.__table__.c.filial_id.nullable
    assert not models.Comanda.__table__.c.filial_id.nullable


def test_vinculos_unicos_sem_cascade_destrutivo(models):
    for model, key in ((models.UsuarioFilial, 'usuario_id'), (models.ClienteFilial, 'cliente_id')):
        table = model.__table__
        assert any(isinstance(c, UniqueConstraint) and list(c.columns.keys()) == [key, 'filial_id'] for c in table.constraints)
        assert all(fk.ondelete is None for fk in table.foreign_keys)
        assert not table.c[key].nullable and not table.c.filial_id.nullable
    assert not models.UsuarioFilial.__table__.c.ativo.nullable


def test_navegacao_bidirecional_sem_duplicar_cadastros(memory_session, models):
    db = memory_session
    empresa = models.Empresa(nome='RelaxaBarber')
    unidades = [models.Filial(nome=nome, empresa=empresa) for nome in ('Inicial', 'Outra teste')]
    cliente = models.Cliente(nome='Cliente', telefone='000000')
    usuario = models.Usuario(nome='Profissional', email='teste@example.test', senha_hash='ficticio', perfil=models.PerfilEnum.BARBEIRO)
    clientes = [models.ClienteFilial(cliente=cliente, filial=f) for f in unidades]
    usuarios = [models.UsuarioFilial(usuario=usuario, filial=f) for f in unidades]
    db.add_all(clientes + usuarios)
    db.commit()
    db.expire_all()
    assert len(cliente.filiais) == len(usuario.filiais) == 2
    assert len(empresa.filiais) == 2
    for filial in empresa.filiais:
        assert filial.clientes[0].cliente is cliente
        assert filial.usuarios[0].usuario is usuario
        assert filial.clientes[0] in cliente.filiais
        assert filial.usuarios[0] in usuario.filiais
        assert filial.empresa is empresa
    assert db.query(models.Cliente).count() == db.query(models.Usuario).count() == 1


def test_exclusao_orm_nao_apaga_vinculos_carregados(memory_session, models):
    import pytest
    from sqlalchemy.exc import IntegrityError
    db = memory_session
    filial = models.Filial(nome='Inicial', empresa=models.Empresa(nome='RelaxaBarber'))
    cliente = models.Cliente(nome='Cliente', telefone='000001')
    vinculo = models.ClienteFilial(cliente=cliente, filial=filial)
    db.add(vinculo)
    db.commit()
    assert cliente.filiais == [vinculo]
    db.delete(cliente)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert db.query(models.ClienteFilial).count() == 1
