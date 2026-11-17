import { MarcaEstabelecimento } from '../../components/MarcaEstabelecimento';
import { useEffect, useRef, useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import axios from 'axios';
import { solicitarTrocaEmail, confirmarTrocaEmail, perfilCliente } from '../../services/portalCliente';
import type { PerfilCliente } from '../../services/portalCliente';
import { mensagemErro } from '../../services/erros';
import './portal.css';

export function TrocaEmailCliente() {
  const [cliente, setCliente] = useState<PerfilCliente | null>(null); const [novo, setNovo] = useState('');
  const [semSessao, setSemSessao] = useState(false); const [reauth, setReauth] = useState(false);
  const [codigo, setCodigo] = useState(''); const [id, setId] = useState('');
  const [etapa, setEtapa] = useState<'pedido' | 'atual' | 'novo' | 'fim'>('pedido');
  const [mensagem, setMensagem] = useState(''); const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false); const [incerto, setIncerto] = useState(false); const trava = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    perfilCliente(controller.signal).then(perfil => { if (!controller.signal.aborted) setCliente(perfil); })
      .catch(falha => { if (!controller.signal.aborted) { if (axios.isAxiosError(falha) && falha.response?.status === 401) setSemSessao(true); else setErro(mensagemErro(falha, 'Não foi possível validar seu acesso.')); } });
    return () => controller.abort();
  }, []);
  async function enviar(e: React.FormEvent) {
    e.preventDefault(); if (trava.current || incerto) return;
    trava.current = true; setOcupado(true); setErro('');
    try {
      if (etapa === 'pedido') {
        const resposta = await solicitarTrocaEmail(novo);
        setId(resposta.solicitacao_id); setMensagem(resposta.mensagem); setEtapa('atual');
      } else if (etapa === 'atual' || etapa === 'novo') {
        const resposta = await confirmarTrocaEmail(etapa, id, codigo);
        setCodigo(''); setMensagem(resposta.mensagem); setEtapa(etapa === 'atual' ? 'novo' : 'fim');
      }
    } catch (falha) {
      if (axios.isAxiosError(falha) && falha.response?.status === 401) setSemSessao(true);
      if (axios.isAxiosError(falha) && falha.response?.status === 403) setReauth(true);
      const desconhecido = axios.isAxiosError(falha) && (!falha.response || falha.response.status >= 500);
      setIncerto(desconhecido);
      setErro(mensagemErro(falha, 'Não foi possível concluir a troca.') + (desconhecido ? ' Não repita o pedido: confira seu e-mail e tente entrar antes de reiniciar.' : ''));
    } finally { trava.current = false; setOcupado(false); }
  }
  if (semSessao) return <Navigate to="/cliente/entrar" replace state={{ mensagem: 'Entre na sua conta para alterar o e-mail. Se esqueceu a senha, recupere pelo e-mail atual.' }} />;
  return <main className="portal-cliente"><header><Link to="/cliente/conta"><MarcaEstabelecimento /></Link></header>
    <section className="portal-cartao"><h1>Alterar e-mail</h1>
      <p>Esta alteração exige login realizado nos últimos dez minutos e confirmação nos dois endereços. Se esqueceu a senha, recupere pelo e-mail atual e entre novamente. Sem acesso ao e-mail atual, procure a recepção.</p>
      {mensagem && <p role="status">{mensagem}</p>}{erro && <p role="alert">{erro}</p>}
      {!cliente && !erro && <p role="status">Validando seu acesso…</p>}
      {reauth && <p><Link to="/cliente/entrar">Entrar novamente para confirmar minha identidade</Link></p>}
      {cliente && etapa !== 'fim' && <form onSubmit={e => void enviar(e)}><fieldset disabled={ocupado || incerto || reauth}>
        <legend>{etapa === 'pedido' ? 'Endereços de e-mail' : etapa === 'atual' ? 'Confirme o e-mail atual' : 'Confirme o novo e-mail'}</legend>
        {etapa === 'pedido' ? <><p>E-mail atual confirmado: {cliente.email}</p>
          <label>Novo e-mail<input type="email" required maxLength={255} autoComplete="off" value={novo} onChange={e => setNovo(e.target.value)} /></label></>
          : <><p>Use o código recebido no {etapa === 'atual' ? 'endereço atual' : 'novo endereço'}. Ele expira em dez minutos e admite até cinco tentativas.</p>
            <label>Código recebido<input required type="password" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={codigo} onChange={e => setCodigo(e.target.value)} /></label></>}
        <button type="submit">{ocupado ? 'Aguarde…' : etapa === 'pedido' ? 'Enviar código ao e-mail atual' : 'Confirmar código'}</button>
      </fieldset></form>}
      {etapa === 'fim' && <p>Entre novamente com o e-mail atualizado. Todas as sessões anteriores foram encerradas.</p>}
      <nav aria-label="Acesso do cliente"><Link to="/cliente/entrar">Entrar</Link><Link to="/cliente/recuperar">Recuperar senha</Link></nav>
    </section></main>;
}
