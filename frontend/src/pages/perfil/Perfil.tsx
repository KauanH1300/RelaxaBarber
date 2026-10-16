import { nomesPerfil, useUsuario } from '../../services/usuario';

export function Perfil() {
  const usuario = useUsuario();
  return (
    <section>
      <h1>Meu perfil</h1>
      <dl>
        <dt>Nome</dt><dd>{usuario.nome}</dd>
        <dt>E-mail</dt><dd>{usuario.email}</dd>
        <dt>Telefone</dt><dd>{usuario.telefone || 'Não informado'}</dd>
        <dt>Perfil</dt><dd>{nomesPerfil[usuario.perfil]}</dd>
        <dt>Situação</dt><dd>{usuario.ativo ? 'Ativo' : 'Inativo'}</dd>
        <dt>Data de cadastro</dt><dd>{new Date(usuario.data_cadastro).toLocaleDateString('pt-BR')}</dd>
      </dl>
    </section>
  );
}
