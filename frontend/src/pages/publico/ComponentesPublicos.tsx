import { Link } from 'react-router-dom';
import { estabelecimento } from '../../config/identidade';
import { MarcaEstabelecimento } from '../../components/MarcaEstabelecimento';

export function CabecalhoPublico() {
  return <header className="publico-header"><Link to="/" className="publico-marca" aria-label={`${estabelecimento.nome} · Início`}><MarcaEstabelecimento /></Link>
    <nav aria-label="Navegação principal"><a href="/#servicos">Serviços</a><a href="/#equipe">Equipe</a><Link to="/cliente/entrar">Minha conta</Link><Link className="publico-botao" to="/agendar">Agendar horário <span aria-hidden="true">↗</span></Link></nav></header>;
}
export function RodapePublico() {
  return <footer className="publico-footer"><Link to="/"><MarcaEstabelecimento /></Link><p>Cuidado nos detalhes. Tempo para você.</p><Link to="/login">Área dos funcionários</Link></footer>;
}
