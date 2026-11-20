import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { AcessoLayout } from './AcessoLayout';
import { redefinirSenhaEquipe, solicitarCodigoEquipe } from '../../services/auth';
import { mensagemErro } from '../../services/erros';

export function RecuperarSenhaEquipe() {
  const [email, setEmail] = useState('');
  const [id, setId] = useState('');
  const [codigo, setCodigo] = useState('');
  const [senha, setSenha] = useState('');
  const [confirmacao, setConfirmacao] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [concluido, setConcluido] = useState(false);
  const trava = useRef(false);

  async function operar(acao: () => Promise<void>) {
    if (trava.current) return;
    trava.current = true;
    setOcupado(true);
    setErro('');
    try { await acao(); }
    catch (falha) { setErro(mensagemErro(falha, 'Não foi possível concluir a operação.')); }
    finally { trava.current = false; setOcupado(false); }
  }

  const solicitar = () => operar(async () => {
    const resposta = await solicitarCodigoEquipe(email.trim());
    setId(resposta.solicitacao_id);
    setCodigo('');
    setMensagem(resposta.mensagem);
  });

  return <AcessoLayout publico="equipe" titulo="Recuperar senha">
    {mensagem && <p role="status">{mensagem}</p>}
    {erro && <p role="alert">{erro}</p>}
    {!concluido && (!id ? <form className="acesso-form" onSubmit={e => { e.preventDefault(); void solicitar(); }}>
      <label>E-mail cadastrado<input type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} disabled={ocupado} /></label>
      <button type="submit" disabled={ocupado}>Solicitar código</button>
    </form> : <form className="acesso-form" onSubmit={e => {
      e.preventDefault();
      if (senha !== confirmacao) { setErro('As senhas precisam coincidir.'); return; }
      void operar(async () => {
        await redefinirSenhaEquipe(id, codigo, senha);
        setConcluido(true); setCodigo(''); setSenha(''); setConfirmacao('');
        setMensagem('Senha redefinida. Entre novamente com a nova senha.');
      });
    }}>
      <fieldset disabled={ocupado}>
        <legend>Redefinir senha da equipe</legend>
        <label>Código<input autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required value={codigo} onChange={e => setCodigo(e.target.value)} /></label>
        <label>Nova senha<input type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={senha} onChange={e => setSenha(e.target.value)} /></label>
        <label>Confirmar nova senha<input type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={confirmacao} onChange={e => setConfirmacao(e.target.value)} /></label>
        <button type="submit">Redefinir senha</button>
        <button type="button" onClick={() => void solicitar()}>Solicitar outro código</button>
        <button type="button" onClick={() => { setId(''); setCodigo(''); setMensagem(''); setErro(''); }}>Trocar e-mail</button>
      </fieldset>
    </form>)}
    <Link to="/login">Voltar ao login</Link>
  </AcessoLayout>;
}
