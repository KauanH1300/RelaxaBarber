import { useEffect, useState } from 'react';
import { NovaSenha } from '../../components/NovaSenha';
import { consultarDispositivos, revogarDispositivos, trocarSenhaEquipe } from '../../services/auth';
import type { DispositivoConfiavel } from '../../services/auth';
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
      {usuario.perfil === 'admin' && <SegurancaAdmin />}
    </section>
  );
}

function SegurancaAdmin() {
  const [itens, setItens] = useState<DispositivoConfiavel[]>([]);
  const [ocupado, setOcupado] = useState(true);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');

  useEffect(() => {
    let ativo = true;
    consultarDispositivos().then(
      dispositivos => { if (ativo) setItens(dispositivos); },
      falha => { if (ativo) setErro(mensagemErro(falha, 'Não foi possível consultar os dispositivos.')); },
    ).finally(() => { if (ativo) setOcupado(false); });
    return () => { ativo = false; };
  }, []);

  async function revogar(id?: string) {
    setOcupado(true);
    setErro('');
    setAviso('');
    try {
      await revogarDispositivos(id);
      setItens(atual => id ? atual.filter(item => item.id !== id) : []);
      setAviso(id ? 'Dispositivo revogado.' : 'Todos os dispositivos foram revogados.');
    } catch (falha) {
      setErro(mensagemErro(falha, 'Não foi possível revogar os dispositivos.'));
    } finally {
      setOcupado(false);
    }
  }

  return <section className="mt-6" aria-labelledby="perfil-seguranca" aria-busy={ocupado}>
    <h2 id="perfil-seguranca">Segurança</h2>
    <h3>Dispositivos confiáveis</h3>
    <p>Ao revogar a confiança, o próximo login nesses dispositivos volta a exigir um código.</p>
    {erro && <p role="alert">{erro}</p>}
    {aviso && <p role="status">{aviso}</p>}
    {ocupado && itens.length === 0 && <p>Carregando dispositivos…</p>}
    {!ocupado && !erro && itens.length === 0 && <p>Nenhum dispositivo confiável.</p>}
    {itens.length > 0 && <>
      <ul className="my-3 grid gap-3">
        {itens.map(item => <li key={item.id}>
          <p>{item.atual ? 'Este dispositivo' : 'Dispositivo confiável'}</p>
          <p>Autorizado em {new Date(item.criado_em).toLocaleString('pt-BR')} · Expira em {new Date(item.expira_em).toLocaleString('pt-BR')}</p>
          <button type="button" disabled={ocupado} onClick={() => void revogar(item.id)}>Revogar dispositivo</button>
        </li>)}
      </ul>
      <button type="button" disabled={ocupado} onClick={() => void revogar()}>Revogar todos os dispositivos</button>
    </>}
  </section>;
}
