import { useNavigate } from 'react-router-dom';
import { useEffect, useRef, useState } from 'react';
import { login, getMe, reenviarLoginAdmin, verificarLoginAdmin } from '../../services/auth';
import { mensagemErro } from '../../services/erros';
import { Icone } from '../../components/Icone';
import { AcessoLayout, CamposLogin } from './AcessoLayout';

export function Login() {
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [verificando, setVerificando] = useState(false);
  const [codigo, setCodigo] = useState('');
  const [confiar, setConfiar] = useState(false);
  const [reenviarEm, setReenviarEm] = useState(0);
  const [agora, setAgora] = useState(Date.now);
  const [aviso, setAviso] = useState('');
  const trava = useRef(false);
  const navigate = useNavigate();
  const espera = Math.max(0, Math.ceil((reenviarEm - agora) / 1000));
  useEffect(() => {
    if (!verificando) return;
    const timer = window.setInterval(() => setAgora(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [verificando]);

  function iniciarEspera(segundos: number) {
    const inicio = Date.now();
    setAgora(inicio);
    setReenviarEm(inicio + segundos * 1000);
  }

  async function executar(acao: () => Promise<void>, mensagem: string) {
    if (trava.current) return;
    trava.current = true;
    setErro(''); setCarregando(true);
    try {
      await acao();
    } catch (err: unknown) {
      setErro(mensagemErro(err, mensagem));
    } finally {
      trava.current = false; setCarregando(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await executar(async () => {
      if (verificando) {
        await verificarLoginAdmin(codigo, confiar);
      } else {
        const resultado = await login(email, senha);
        if ('verificacao_email' in resultado) {
          setSenha('');
          setVerificando(true);
          iniciarEspera(resultado.reenvio_segundos);
          return;
        }
      }
      await getMe();
      navigate('/agendamentos');
    }, 'Erro ao fazer login');
  }

  async function reenviar() {
    await executar(async () => {
      const resultado = await reenviarLoginAdmin();
      setCodigo('');
      iniciarEspera(resultado.reenvio_segundos);
      setAviso('Novo código enviado.');
    }, 'Não foi possível reenviar o código.');
  }

  if (verificando) return <AcessoLayout publico="equipe" titulo="Verifique seu e-mail">
    <p className="acesso-nota">Digite o código de 6 dígitos enviado ao seu e-mail. Ele vale por 5 minutos.</p>
    {erro && <p role="alert">{erro}</p>}
    {aviso && <p role="status">{aviso}</p>}
    <form className="acesso-form" onSubmit={e => void handleSubmit(e)}>
      <fieldset disabled={carregando}>
        <legend className="acesso-sr">Verificação em duas etapas</legend>
        <div className="acesso-campo">
          <label className="acesso-rotulo" htmlFor="login-admin-codigo">Código de verificação</label>
          <div className="acesso-input">
            <input id="login-admin-codigo" autoComplete="one-time-code" inputMode="numeric"
              maxLength={6} pattern="[0-9]{6}" required value={codigo}
              onChange={e => setCodigo(e.target.value.replace(/[^0-9]/g, ''))} />
          </div>
        </div>
        <label><input type="checkbox" checked={confiar} onChange={e => setConfiar(e.target.checked)} /> Confiar neste dispositivo por 30 dias</label>
        <button className="acesso-submit" type="submit">Verificar e entrar<Icone nome="arrow_forward" /></button>
        <button type="button" disabled={espera > 0} onClick={() => void reenviar()}>
          {espera > 0 ? `Reenviar código em ${espera} s` : 'Reenviar código'}
        </button>
        <button type="button" onClick={() => {
          setVerificando(false);
          setCodigo('');
          setConfiar(false);
          setAviso('');
          setErro('');
        }}>Voltar ao login</button>
      </fieldset>
    </form>
  </AcessoLayout>;
  return <AcessoLayout publico="equipe">
    {erro && <p role="alert">{erro}</p>}
    <form className="acesso-form" onSubmit={e => void handleSubmit(e)}><fieldset disabled={carregando}><legend className="acesso-sr">Acesso da equipe</legend>
      <CamposLogin equipe email={email} senha={senha} onEmail={setEmail} onSenha={setSenha} recuperacao="/recuperar-senha" />
      <button className="acesso-submit" type="submit" disabled={carregando}>{carregando ? 'Entrando…' : 'Entrar no Sistema'}<Icone nome="arrow_forward" /></button>
    </fieldset></form>
    <div className="acesso-footer"><span><Icone nome="group" />Ainda não possui conta?</span><span>Cadastro pela administração.</span></div>
  </AcessoLayout>;
}
export default Login;
