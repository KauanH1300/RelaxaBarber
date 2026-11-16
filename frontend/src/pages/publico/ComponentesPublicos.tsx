import { Link } from 'react-router-dom';
import logo from '../../assets/logo.png';

export function CabecalhoPublico() {
  return <header className="publico-header"><Link to="/" className="publico-marca" aria-label="RelaxaBarber · Início"><img src={logo} alt="" /><span>RELAXA<span>BARBEARIA</span></span></Link>
    <nav aria-label="Navegação principal"><a href="/#servicos">Serviços</a><a href="/#equipe">Equipe</a><Link to="/cliente/entrar">Minha conta</Link><Link className="publico-botao" to="/agendar">Agendar horário <span aria-hidden="true">↗</span></Link></nav></header>;
}
export function RodapePublico() {
  return <footer className="publico-footer"><Link to="/">RelaxaBarber <span>· Barbearia</span></Link><p>Cuidado nos detalhes. Tempo para você.</p><Link to="/login">Área dos funcionários</Link></footer>;
}
