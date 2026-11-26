import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MarcaEstabelecimento } from '../../components/MarcaEstabelecimento';
import { estabelecimento } from '../../config/identidade';

export const secoesInicio = [
  ['inicio', 'Início'], ['servicos', 'Serviços'], ['vitrine', 'Vitrine'], ['equipe', 'Barbeiros'],
  ['localizacao', 'Localização e Contato'],
] as const;

export function NavegacaoInicio() {
  const [ativa, setAtiva] = useState('inicio');
  const [aberto, setAberto] = useState(false);
  const header = useRef<HTMLElement>(null);
  const menu = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const elemento = header.current;
    const pagina = elemento?.closest<HTMLElement>(".landing");
    if (!elemento || !pagina) return;
    let quadro = 0;
    const atualizar = () => {
      cancelAnimationFrame(quadro);
      quadro = requestAnimationFrame(() => {
        const altura = elemento.offsetHeight;
        pagina.style.setProperty("--altura-header-real", `${altura}px`);
        const limite = altura + 48;
        const visivel = [...secoesInicio].reverse().find(([id]) => {
          const secao = document.getElementById(id);
          return secao && secao.getBoundingClientRect().top <= limite;
        });
        const localizacao = document.getElementById('localizacao');
        const fim = localizacao && localizacao.getBoundingClientRect().bottom <= limite;
        setAtiva(fim ? '' : visivel?.[0] ?? 'inicio');
      });
    };
    const observador = new ResizeObserver(atualizar);
    observador.observe(elemento);
    const conteudo = document.getElementById('conteudo');
    if (conteudo) observador.observe(conteudo);
    window.addEventListener('scroll', atualizar, { passive: true });
    window.addEventListener('resize', atualizar);
    atualizar();
    return () => {
      observador.disconnect();
      window.removeEventListener('scroll', atualizar);
      window.removeEventListener('resize', atualizar);
      cancelAnimationFrame(quadro);
    };
  }, []);

  return <header ref={header} className="landing-header" onKeyDown={evento => {
    if (evento.key === 'Escape' && aberto) {
      setAberto(false);
      menu.current?.focus();
    }
  }}>
    <div className="landing-container landing-header-row">
      <a href="#inicio" onClick={() => setAberto(false)} aria-label={`${estabelecimento.nome}, início`}>
        <MarcaEstabelecimento />
      </a>
      <nav id="landing-menu" className="landing-nav" data-aberto={aberto} aria-label="Navegação principal">
        {secoesInicio.map(([id, rotulo]) => <a key={id} href={`#${id}`}
            aria-current={ativa === id ? 'location' : undefined}
            onClick={() => setAberto(false)}>{rotulo}</a>)}
        <Link className="landing-conta-mobile" to="/cliente/entrar">Minha conta</Link>
      </nav>
      <div className="flex items-center gap-2">
        <Link to="/agendar" className="landing-btn landing-btn-ouro">Agendar horário</Link>
        <Link to="/cliente/entrar" className="landing-conta" aria-label="Minha conta" title="Minha conta">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
            <circle cx="12" cy="8" r="3" /><path d="M5 20v-2a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v2" />
          </svg>
        </Link>
        <button ref={menu} type="button" className="landing-menu-toggle" aria-expanded={aberto}
          aria-controls="landing-menu" aria-label={aberto ? 'Fechar menu' : 'Abrir menu'}
          onClick={() => setAberto(!aberto)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d={aberto ? 'M6 6l12 12M18 6 6 18' : 'M4 6h16M4 12h16M4 18h16'} />
          </svg>
        </button>
      </div>
    </div>
  </header>;
}
