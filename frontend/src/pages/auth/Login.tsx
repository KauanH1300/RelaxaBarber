import { useNavigate } from 'react-router-dom';
import { useRef, useState } from 'react';
import { login, getMe } from '../../services/auth';
import { mensagemErro } from '../../services/erros';
import { Icone } from '../../components/Icone';
import { AcessoLayout, CamposLogin } from './AcessoLayout';

export function Login() {
  const [email, setEmail] = useState('');
  const [senha, setSenha] = useState('');
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(false);
  const trava = useRef(false);
  const navigate = useNavigate();
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (trava.current) return;
    trava.current = true;
    setErro(''); setCarregando(true);
    try {
      await login(email, senha);
      await getMe();
      navigate('/agendamentos');
    } catch (err: unknown) {
      setErro(mensagemErro(err, 'Erro ao fazer login'));
    } finally {
      trava.current = false; setCarregando(false);
    }
  };
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
