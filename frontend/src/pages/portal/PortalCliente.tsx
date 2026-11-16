import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import * as portal from '../../services/portalCliente';
import type { PerfilCliente } from '../../services/portalCliente';
import { mensagemErro } from '../../services/erros';
import './portal.css';

export function AcessoCliente({ modo }: { modo: 'entrar' | 'cadastro' | 'recuperar' | 'ativar' | 'redefinir' }) {
  const navigate = useNavigate(); const location = useLocation();
  const [nome, setNome] = useState(''); const [telefone, setTelefone] = useState('');
  const [email, setEmail] = useState(''); const [senha, setSenha] = useState(''); const [codigo, setCodigo] = useState('');
  const [id, setId] = useState((location.state as { solicitacao_id?: string } | null)?.solicitacao_id ?? '');
  const [erro, setErro] = useState(''); const [mensagem, setMensagem] = useState((location.state as { mensagem?: string } | null)?.mensagem ?? '');
  const [ocupado, setOcupado] = useState(false); const [incerto, setIncerto] = useState(false); const trava = useRef(false);
  const confirma = modo === 'ativar' || modo === 'redefinir';
  const titulos = { entrar: 'Entre na sua conta', cadastro: 'Crie sua conta', recuperar: 'Recupere seu acesso', ativar: 'Confirme seu e-mail', redefinir: 'Defina sua nova senha' };
  async function enviar(e: React.FormEvent) {
    e.preventDefault(); if (trava.current || incerto) return;
    trava.current = true; setOcupado(true); setErro(''); setMensagem('');
    try {
      if (modo === 'entrar') { await portal.entrarCliente(email, senha); navigate('/cliente', { replace: true }); }
      else if (modo === 'cadastro' || modo === 'recuperar') {
        const resposta = modo === 'cadastro' ? await portal.cadastrarConta({ nome, telefone, email, senha }) : await portal.recuperarConta(email);
        setSenha('');
        navigate(modo === 'cadastro' ? '/cliente/ativar' : '/cliente/redefinir', { state: resposta });
      } else {
        const resposta = modo === 'ativar' ? await portal.confirmarConta(id, codigo) : await portal.redefinirSenhaCliente(id, codigo, senha);
        setSenha(''); setCodigo(''); navigate('/cliente/entrar', { state: resposta, replace: true });
      }
    } catch (falha) {
      const desconhecido = axios.isAxiosError(falha) && (!falha.response || falha.response.status >= 500);
      // Não repetir automaticamente pedidos de código, confirmação ou redefinição.
      setIncerto(desconhecido && !falhaIsEntregaIndisponivel(falha));
      setErro(mensagemErro(falha, 'Não foi possível concluir. Tente novamente mais tarde.') + (desconhecido && !falhaIsEntregaIndisponivel(falha) ? ' O resultado não foi confirmado. Confira seu e-mail ou tente entrar antes de reiniciar o pedido.' : ''));
    } finally { trava.current = false; setOcupado(false); }
  }
  return <main className="portal-cliente"><header><Link to="/cliente/entrar">RelaxaBarber · Clientes</Link><Link to="/login">Acesso da equipe</Link></header>
    <section className="portal-cartao"><p className="portal-sobrancelha">Seu espaço na RelaxaBarber</p><h1>{titulos[modo]}</h1>
      {mensagem && <p role="status">{mensagem}</p>}{erro && <p role="alert">{erro}</p>}
      {modo === 'cadastro' && <p>Já passou pela recepção? Use o mesmo e-mail e telefone para vincular seu cadastro. A ativação exige o código enviado por e-mail.</p>}
      {modo === 'recuperar' && <p>Informe seu e-mail. A resposta será a mesma independentemente da existência de uma conta.</p>}
      {confirma && <p>O código tem seis dígitos, expira em dez minutos e só pode ser usado uma vez. Não compartilhe com ninguém.</p>}
      <form onSubmit={e => void enviar(e)}><fieldset disabled={ocupado || incerto}>
        <legend className="portal-sr">Dados de acesso</legend>
        {modo === 'cadastro' && <><label>Nome<input required maxLength={150} autoComplete="name" value={nome} onChange={e => setNome(e.target.value)} /></label><label>Telefone com DDD<input required type="tel" maxLength={25} autoComplete="tel" value={telefone} onChange={e => setTelefone(e.target.value)} /></label></>}
        {!confirma && <label>E-mail<input required type="email" maxLength={255} autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} /></label>}
        {confirma && <><label>Identificador do pedido<input required value={id} onChange={e => setId(e.target.value)} autoComplete="off" /></label><label>Código recebido<input required inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={codigo} onChange={e => setCodigo(e.target.value)} /></label></>}
        {['entrar','cadastro','redefinir'].includes(modo) && <label>{modo === 'redefinir' ? 'Nova senha' : 'Senha'}<input required type="password" minLength={modo === 'entrar' ? 1 : 12} maxLength={128} autoComplete={modo === 'entrar' ? 'current-password' : 'new-password'} value={senha} onChange={e => setSenha(e.target.value)} />{modo !== 'entrar' && <small>Use ao menos 12 caracteres.</small>}</label>}
        <button type="submit">{ocupado ? 'Aguarde…' : modo === 'entrar' ? 'Entrar' : confirma ? 'Confirmar' : 'Enviar código'}</button>
      </fieldset></form>
      <nav aria-label="Acesso do cliente"><Link to="/cliente/entrar">Entrar</Link><Link to="/cliente/cadastro">Criar conta</Link><Link to="/cliente/recuperar">Esqueci minha senha</Link><Link to="/cliente/trocar-email">Trocar e-mail</Link></nav>
      <p className="portal-ajuda">Se o e-mail não chegar ou seus dados estiverem diferentes, procure a recepção. O acesso só é ativado após a confirmação.</p>
    </section></main>;
}

function falhaIsEntregaIndisponivel(falha: unknown) {
  return axios.isAxiosError(falha) && falha.response?.status === 503 && typeof falha.response.data?.detail === 'string' && falha.response.data.detail.includes('envio de códigos');
}

export function InicioCliente() {
  const location = useLocation(); const navigate = useNavigate();
  const [cliente, setCliente] = useState<PerfilCliente | null>(null); const [semSessao, setSemSessao] = useState(false);
  const [erro, setErro] = useState(''); const [saindo, setSaindo] = useState(false); const trava = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    portal.perfilCliente(controller.signal).then(dados => { if (!controller.signal.aborted) setCliente(dados); })
      .catch(falha => { if (!controller.signal.aborted) { if (axios.isAxiosError(falha) && falha.response?.status === 401) setSemSessao(true); else setErro(mensagemErro(falha, 'Não foi possível consultar sua conta.')); } });
    return () => controller.abort();
  }, []);
  async function sair() {
    if (trava.current) return;
    trava.current = true; setSaindo(true); setErro('');
    try { await portal.sairCliente(); navigate('/cliente/entrar', { replace: true }); }
    catch (falha) { setErro(mensagemErro(falha, 'Não foi possível encerrar a sessão. Tente novamente.')); }
    finally { trava.current = false; setSaindo(false); }
  }
  if (semSessao) return <Navigate to="/cliente/entrar" replace />;
  return <main className="portal-cliente"><header><Link to="/cliente">RelaxaBarber · Clientes</Link><button disabled={saindo} onClick={() => void sair()}>{saindo ? 'Saindo…' : 'Sair'}</button></header>
    <section className="portal-cartao">{erro && <p role="alert">{erro}</p>}{!cliente && !erro && <p role="status">Validando seu acesso…</p>}
      {cliente && <><nav aria-label="Área do cliente"><Link to="/cliente">Início</Link><Link to="/cliente/conta">Minha conta</Link></nav>
        <p className="portal-sobrancelha">Bem-vindo à RelaxaBarber</p><h1>{location.pathname.endsWith('/conta') ? 'Minha conta' : `Olá, ${cliente.nome}`}</h1>
        <p>Seu acesso está ativo. Confira os dados do seu cadastro.</p><dl><dt>Nome</dt><dd>{cliente.nome}</dd><dt>E-mail confirmado</dt><dd>{cliente.email}</dd><dt>Telefone</dt><dd>{cliente.telefone}</dd></dl>
        <p>Para corrigir seus demais dados, procure a recepção.</p><Link to="/cliente/trocar-email">Trocar e-mail</Link><Link to="/cliente/recuperar">Redefinir minha senha</Link></>}
    </section></main>;
}
