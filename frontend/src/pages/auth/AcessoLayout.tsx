import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { NavegacaoInicio } from '../publico/NavegacaoInicio';
import { Icone } from '../../components/Icone';
import { estabelecimento, software } from '../../config/identidade';
import { sufixoRetorno } from '../../services/agendamentoPublico';
import './AcessoLayout.css';

export function AcessoLayout({ publico, children, titulo = 'Bem-vindo de volta' }: { publico: 'cliente' | 'equipe'; children: ReactNode; titulo?: string }) {
  const retorno = sufixoRetorno(useLocation().search);
  return <div className="acesso landing-acesso"><NavegacaoInicio paginaInicial={false} />
    <main className="acesso-main"><div className="acesso-card"><aside className="acesso-brand" aria-label={estabelecimento.nome}><span className="acesso-sinal" aria-hidden="true" /><div className="acesso-manifesto"><div className="acesso-logo"><img src={estabelecimento.logo} alt={`Logo ${estabelecimento.nome}`} /></div><h2>{estabelecimento.nome}</h2><p className="acesso-legenda">Sistema de Gestão &amp; Agendamento</p><span className="acesso-linha" /><p className="acesso-frase">Tradição artesanal, precisão e experiência singular em cada detalhe.</p><p className="acesso-descricao">Atendimento e agendamento na {estabelecimento.nome}.</p></div></aside>
      <section className="acesso-conteudo" aria-labelledby="acesso-titulo"><div className="acesso-intro"><p className="acesso-selo"><strong>{publico === 'equipe' ? software.nome : estabelecimento.nome}</strong>{publico === 'equipe' && <><span>•</span>Acesso restrito</>}</p><h1 id="acesso-titulo">{titulo}</h1><p>{publico === 'equipe' ? 'Acesse a gestão da' : 'Acesse sua conta de cliente na'} <strong>{estabelecimento.nome}</strong>.</p></div>
        <nav className="acesso-alternancia" aria-label="Tipo de acesso"><Link to={'/cliente/entrar' + retorno} aria-current={publico === 'cliente' ? 'page' : undefined}><Icone nome="person" />Clientes</Link><Link to={'/login' + retorno} aria-current={publico === 'equipe' ? 'page' : undefined}><Icone nome="group" />Equipe da barbearia</Link></nav>
        {children}
      </section></div></main>
  </div>;
}

export function CamposLogin({ equipe = false, email, senha, onEmail, onSenha, recuperacao }: { equipe?: boolean; email: string; senha: string; onEmail: (valor: string) => void; onSenha: (valor: string) => void; recuperacao?: string }) {
  const [visivel, setVisivel] = useState(false);
  return <><div className="acesso-campo"><div className="acesso-rotulo"><label htmlFor="acesso-email">E-mail</label><span>{equipe ? 'Gestão & Staff' : 'Conta de cliente'}</span></div><div className="acesso-input"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 6 9 7 9-7" /></svg><input id="acesso-email" type="email" required maxLength={255} autoComplete="username" placeholder="seuemail@exemplo.com" value={email} onChange={e => onEmail(e.target.value)} /></div></div>
    <div className="acesso-campo"><div className="acesso-rotulo"><label htmlFor="acesso-senha">Chave de Acesso / Senha</label>{recuperacao && <Link to={recuperacao}>Esqueceu a senha?</Link>}</div><div className="acesso-input"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V6a4 4 0 0 1 8 0v4 M12 14v3" /></svg><input id="acesso-senha" type={visivel ? 'text' : 'password'} required maxLength={128} autoComplete="current-password" placeholder="••••••••••••" value={senha} onChange={e => onSenha(e.target.value)} /><button className="acesso-visibilidade" type="button" aria-label={visivel ? 'Ocultar senha' : 'Mostrar senha'} aria-pressed={visivel} onClick={() => setVisivel(!visivel)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />{visivel && <path d="m3 3 18 18" />}</svg></button></div></div></>;
}
