import { assinaturaSoftware, estabelecimento } from '../config/identidade';
import './MarcaEstabelecimento.css';

export function MarcaEstabelecimento() {
  return <span className="marca-estabelecimento"><img src={estabelecimento.logo} alt="" /><span><strong>{estabelecimento.nome}</strong><small>{assinaturaSoftware}</small></span></span>;
}
