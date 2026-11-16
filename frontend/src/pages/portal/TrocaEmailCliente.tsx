import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { solicitarTrocaEmail, confirmarTrocaEmail } from '../../services/portalCliente';
import { mensagemErro } from '../../services/erros';
import './portal.css';

export function TrocaEmailCliente() {
  const [email, setEmail] = useState(''); const [novo, setNovo] = useState('');
  const [codigo, setCodigo] = useState(''); const [id, setId] = useState('');
  const [etapa, setEtapa] = useState<'pedido' | 'atual' | 'novo' | 'fim'>('pedido');
  const [mensagem, setMensagem] = useState(''); const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false); const [incerto, setIncerto] = useState(false); const trava = useRef(false);
  async function enviar(e: React.FormEvent) {
    e.preventDefault(); if (trava.current || incerto) return;
    trava.current = true; setOcupado(true); setErro('');
    try {
      if (etapa === 'pedido') {
        const resposta = await solicitarTrocaEmail(email, novo);
        setId(resposta.solicitacao_id); setMensagem(resposta.mensagem); setEtapa('atual');
      } else if (etapa === 'atual' || etapa === 'novo') {
        const resposta = await confirmarTrocaEmail(etapa, id, codigo);
        setCodigo(''); setMensagem(resposta.mensagem); setEtapa(etapa === 'atual' ? 'novo' : 'fim');
      }
    } catch (falha) {
      const desconhecido = axios.isAxiosError(falha) && (!falha.response || falha.response.status >= 500);
      setIncerto(desconhecido);
      setErro(mensagemErro(falha, 'Não foi possível concluir a troca.') + (desconhecido ? ' Não repita o pedido: confira seu e-mail e tente entrar antes de reiniciar.' : ''));
    } finally { trava.current = false; setOcupado(false); }
  }
  return <main className="portal-cliente"><header><Link to="/cliente/entrar">RelaxaBarber · Clientes</Link></header>
    <section className="portal-cartao"><h1>Trocar meu e-mail</h1>
      <p>Confirme sua identidade no endereço atual e depois no novo. Não é necessário lembrar a senha. Sem acesso ao e-mail atual, procure a recepção.</p>
      {mensagem && <p role="status">{mensagem}</p>}{erro && <p role="alert">{erro}</p>}
      {etapa !== 'fim' && <form onSubmit={e => void enviar(e)}><fieldset disabled={ocupado || incerto}>
        <legend>{etapa === 'pedido' ? 'Endereços de e-mail' : etapa === 'atual' ? 'Confirme o e-mail atual' : 'Confirme o novo e-mail'}</legend>
        {etapa === 'pedido' ? <><label>E-mail atual<input type="email" required maxLength={255} autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
          <label>Novo e-mail<input type="email" required maxLength={255} autoComplete="off" value={novo} onChange={e => setNovo(e.target.value)} /></label></>
          : <><p>Use o código recebido no {etapa === 'atual' ? 'endereço atual' : 'novo endereço'}. Ele expira em dez minutos e admite até cinco tentativas.</p>
            <label>Código recebido<input required type="password" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} autoComplete="one-time-code" value={codigo} onChange={e => setCodigo(e.target.value)} /></label></>}
        <button type="submit">{ocupado ? 'Aguarde…' : etapa === 'pedido' ? 'Enviar código ao e-mail atual' : 'Confirmar código'}</button>
      </fieldset></form>}
      {etapa === 'fim' && <p>Esqueceu a senha? Recupere seu acesso usando o novo e-mail.</p>}
      <nav aria-label="Acesso do cliente"><Link to="/cliente/entrar">Entrar</Link><Link to="/cliente/recuperar">Recuperar senha</Link></nav>
    </section></main>;
}
