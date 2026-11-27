import { useState } from 'react';
import { NovaSenha } from '../../components/NovaSenha';
import { trocarSenhaEquipe } from '../../services/auth';
import { mensagemErro } from '../../services/erros';
import { nomesPerfil, useUsuario } from '../../services/usuario';

export function Perfil() {
  const usuario = useUsuario();
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);
  async function trocar(evento: React.FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const atual = String(new FormData(evento.currentTarget).get('senhaAtual'));
    setSalvando(true);
    setErro('');
    try {
      await trocarSenhaEquipe(atual, senha);
    } catch (falha) {
      setErro(mensagemErro(falha, 'Não foi possível trocar a senha.'));
    } finally {
      setSalvando(false);
    }
  }
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
      <details className="mt-4">
        <summary>Alterar senha</summary>
        <form className="mt-2 grid max-w-md gap-3" onSubmit={trocar} aria-busy={salvando}>
          <p>Após a troca, entre novamente com a nova senha.</p>
          <label>Senha atual<input className="ml-2" type="password" name="senhaAtual"
            autoComplete="current-password" maxLength={128} required /></label>
          <NovaSenha valor={senha} alterar={setSenha} minimo={15} />
          {erro && <p role="alert">{erro}</p>}
          <button type="submit" disabled={salvando}>{salvando ? 'Salvando…' : 'Salvar nova senha'}</button>
        </form>
      </details>
    </section>
  );
}
