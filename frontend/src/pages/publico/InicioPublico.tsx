import { estabelecimento } from '../../config/identidade';
import { Link } from 'react-router-dom';
import rodrigo from '../../assets/rodrigo_relaxa.png';
import higor from '../../assets/higor_rodrigo.png';
import { CabecalhoPublico, RodapePublico } from './ComponentesPublicos';
import { useCatalogoPublico, precoPublico } from './useCatalogoPublico';
import './publico.css';

export function InicioPublico() {
  const { servicos, estado } = useCatalogoPublico();
  return <div className="publico"><a className="publico-pular" href="#conteudo">Pular para o conteúdo</a><CabecalhoPublico />
    <main id="conteudo"><section className="publico-hero"><div className="publico-hero-texto"><p className="publico-selo">RELAXA BARBEARIA · DESDE 2019</p>
      <h1>Seu estilo.<br />Nosso cuidado.<br /><em>Seu momento.</em></h1>
      <p>Uma pausa na rotina, um corte com personalidade. Na Relaxa, cada detalhe faz parte da experiência.</p>
      <div className="publico-acoes"><Link to="/agendar" className="publico-botao">Agendar horário <span aria-hidden="true">↗</span></Link><a href="#servicos" className="publico-text-link">Conheça nossos serviços ↓</a></div>
      <p className="publico-nota">Escolha seu serviço e um horário livre. Entre na sua conta apenas para confirmar.</p></div>
      <div className="publico-hero-foto"><img src={rodrigo} alt={`Rodrigo Relaxa, da equipe ${estabelecimento.nome}`} fetchPriority="high" /><div><span>O cuidado está nos detalhes.</span><strong>RELAXA. VOCÊ ESTÁ EM BOAS MÃOS.</strong></div></div></section>
      <div className="publico-faixa"><span>CORTE & ESTILO</span><span aria-hidden="true">✦</span><span>BARBA & CUIDADO</span><span aria-hidden="true">✦</span><span>DO SEU JEITO</span></div>
      <section id="servicos" className="publico-secao"><div className="publico-titulo"><div><p className="publico-selo">01 / NOSSOS SERVIÇOS</p><h2>Um novo visual.<br /><em>A mesma essência.</em></h2></div><p>Escolha o cuidado que combina com você. Consulte os valores e o tempo estimado de cada serviço.</p></div>
        {estado === 'carregando' && <p role="status">Carregando serviços…</p>}{estado === 'erro' && <p role="alert">Não foi possível carregar o catálogo. Os serviços estarão disponíveis quando a conexão for restabelecida.</p>}
        {estado === 'pronto' && !servicos.length && <p>Nenhum serviço disponível no catálogo no momento.</p>}
        <div className="publico-servicos">{servicos.map((s, i) => <article key={s.id}><span className="publico-numero">{String(i + 1).padStart(2, '0')}</span><h3>{s.nome}</h3><p>{s.tempo_estimado} min de cuidado</p><div><strong>{precoPublico(s.preco)}</strong><Link to={`/agendar?servico=${encodeURIComponent(s.id)}`} aria-label={`Escolher ${s.nome}`}>Escolher <span aria-hidden="true">↗</span></Link></div></article>)}</div></section>
      <section id="equipe" className="publico-secao publico-equipe"><div className="publico-titulo"><div><p className="publico-selo">02 / QUEM CUIDA DE VOCÊ</p><h2>Mãos que fazem<br /><em>a diferença.</em></h2></div><p>Conheça a equipe da {estabelecimento.nome}. No agendamento, consulte os profissionais habilitados e os horários disponíveis para seu serviço.</p></div>
        <div className="publico-profissionais">{[{ nome: 'Rodrigo Relaxa', foto: rodrigo }, { nome: 'Higor Rodrigo', foto: higor }].map(p => <article key={p.nome}><img src={p.foto} alt={p.nome} loading="lazy" /><div><h3>{p.nome}</h3><p>Equipe {estabelecimento.nome}</p></div></article>)}</div></section>
      <section className="publico-convite"><p className="publico-selo">RESERVE UM TEMPO PARA VOCÊ</p><h2>Seu próximo visual<br />começa por aqui.</h2><Link to="/agendar" className="publico-botao">Escolher meu atendimento ↗</Link><p>Monte suas preferências sem precisar entrar.</p></section>
    </main><RodapePublico /></div>;
}
