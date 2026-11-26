import { useEffect, useState } from 'react';
import { ContatoInicio, HorariosInicio } from './ContatoInicio';
import { Link, useLocation } from 'react-router-dom';
import fotoSobre from '../../assets/landing-sobre.jpg';
import { Icone } from '../../components/Icone';
import { MarcaEstabelecimento } from '../../components/MarcaEstabelecimento';
import { estabelecimento, software } from '../../config/identidade';
import { NavegacaoInicio, secoesInicio } from './NavegacaoInicio';
import { VitrineInicio } from './VitrineInicio';
import { UnidadeInicio, useFiliaisInicio } from './UnidadeInicio';
import { useCatalogoPublico, precoPublico } from './useCatalogoPublico';
import './inicioPublico.css';

const diferenciais = [
  ['content_cut', 'Profissionais qualificados', 'Atenção ao seu estilo e às suas preferências.'],
  ['info', 'Ambiente acolhedor', 'Um espaço pensado para você relaxar durante o atendimento.'],
  ['task_alt', 'Higiene e cuidado', 'O cuidado está presente em cada etapa do atendimento.'],
  ['schedule', 'Agendamento facilitado', 'Escolha o melhor dia e horário pelo site.'],
];

export function InicioPublico() {
  const { servicos, estado } = useCatalogoPublico();
  const [catalogoCompleto, setCatalogoCompleto] = useState(false);
  const { filiais, estado: estadoFiliais } = useFiliaisInicio();
  const { hash, search } = useLocation();
  const [filialId, setFilialId] = useState('');
  const filialSolicitada = filialId || new URLSearchParams(search).get('filial_id');

  useEffect(() => {
    if (hash !== '#vitrine') return;
    const quadro = requestAnimationFrame(() => document.getElementById('vitrine')?.scrollIntoView());
    return () => cancelAnimationFrame(quadro);
  }, [hash, estado]);
  const filial = filiais.find(item => item.id === filialSolicitada) ?? filiais[0];

  return <div className="landing">
    <a className="landing-pular" href="#conteudo">Pular para o conteúdo</a>
    <NavegacaoInicio />
    <main id="conteudo" tabIndex={-1}>
      <section tabIndex={-1} id="inicio" className="landing-hero text-center" aria-labelledby="landing-titulo">
        <div className="landing-container">
          <h1 id="landing-titulo">Seu estilo merece<br /><em>atenção em cada detalhe.</em></h1>
          <p>Corte de precisão, barba alinhada e uma experiência de cuidado. Resgatamos a essência da barbearia clássica com o conforto que você merece.</p>
          <div className="landing-acoes">
            <Link to="/agendar" className="landing-btn landing-btn-ouro"><Icone nome="calendar_today" /> Agendar horário</Link>
            <a href="#servicos" className="landing-btn"><span className="landing-ouro"><Icone nome="content_cut" /></span> Conheça nossos serviços</a>
          </div>
        </div>
      </section>

      <section tabIndex={-1} id="sobre" className="landing-secao" aria-labelledby="landing-sobre">
        <div className="landing-container">
          <div className="landing-intro">
            <p className="landing-selo">A barbearia</p>
            <h2 id="landing-sobre">Mais que um corte, uma experiência de cuidado</h2>
            <p>Valorizamos a tradição da boa barbearia, o conforto do ambiente e a dedicação da nossa equipe em oferecer o melhor atendimento no seu dia a dia.</p>
          </div>
          <div className="landing-sobre">
            <figure className="landing-foto">
              <img src={fotoSobre} alt="Barbeiro aparando a barba de um cliente na Relaxa o Bigode" loading="lazy" />
              <figcaption>
                <p className="landing-selo">Cuidado em cada detalhe</p>
                <h3>Seu estilo, sua identidade</h3>
                <p>Cada atendimento é feito com calma e atenção para valorizar seu estilo e suas preferências.</p>
              </figcaption>
            </figure>
            <div className="landing-diferenciais">
              {diferenciais.map(([icone, titulo, texto]) => <article className="landing-card" key={titulo}>
                <span className="landing-icone"><Icone nome={icone} /></span>
                <h3>{titulo}</h3><p>{texto}</p>
              </article>)}
            </div>
          </div>
        </div>
      </section>

      <section tabIndex={-1} id="servicos" className="landing-secao landing-escura" aria-labelledby="landing-servicos">
        <div className="landing-container">
          <div className="landing-titulo-lateral">
            <div><p className="landing-selo">Serviços</p><h2 id="landing-servicos">Conheça nossos serviços</h2></div>
            <p>Escolha o cuidado que combina com você. Consulte valores e tempos estimados.</p>
          </div>
          {estado === 'carregando' && <p role="status">Carregando serviços…</p>}
          {estado === 'erro' && <p role="status">Não foi possível carregar o catálogo. Tente novamente em instantes.</p>}
          {estado === 'pronto' && !servicos.length && <p>Nenhum serviço disponível no catálogo no momento.</p>}
          <div className="landing-servicos" id="landing-lista-servicos">
            {servicos.slice(0, catalogoCompleto ? undefined : 6).map(servico => <article className="landing-card" key={servico.id}>
              <p className="landing-tempo"><span className="landing-ouro"><Icone nome="schedule" /></span> {servico.tempo_estimado} min</p>
              <h3>{servico.nome}</h3>
              {!!servico.categorias?.length && <ul className="mt-2 flex flex-wrap gap-2" aria-label="Categorias do serviço">
                {servico.categorias.map(categoria => <li key={categoria.id}
                  className="rounded bg-white/10 px-2 py-1 text-sm">{categoria.nome}</li>)}
              </ul>}
              <div className="landing-servico-rodape">
                <strong className="landing-ouro">{precoPublico(servico.preco)}</strong>
                <Link className="landing-btn landing-btn-menor" to={`/agendar?servico=${encodeURIComponent(servico.id)}`}
                  aria-label={`Agendar ${servico.nome}`}>Agendar</Link>
              </div>
            </article>)}
          </div>
          {servicos.length > 6 && <div className="landing-acoes">
            <button className="landing-btn landing-ouro" type="button" aria-expanded={catalogoCompleto}
              aria-controls="landing-lista-servicos" onClick={evento => {
                if (catalogoCompleto) evento.currentTarget.closest('section')?.scrollIntoView();
                setCatalogoCompleto(!catalogoCompleto);
              }}>{catalogoCompleto ? 'Mostrar menos serviços' : 'Ver catálogo completo de serviços'}</button>
          </div>}
        </div>
      </section>

      <VitrineInicio filial={filial} filiais={filiais} estado={estadoFiliais} selecionar={setFilialId} />

      <UnidadeInicio filial={filial} filiais={filiais} estado={estadoFiliais} selecionar={setFilialId} />

      <section className="landing-convite landing-secao text-center" aria-labelledby="landing-convite">
        <div className="landing-container">
          <span className="landing-icone"><Icone nome="calendar_today" /></span>
          <h2 id="landing-convite">Que tal renovar seu visual?</h2>
          <p>Escolha seu profissional, o serviço ideal e o melhor horário para você. Entre na sua conta apenas para confirmar.</p>
          <div className="landing-acoes">
            <Link className="landing-btn landing-btn-ouro" to="/agendar">Agendar horário</Link>
            <Link className="landing-btn" to="/cliente/entrar">Minha conta</Link>
          </div>
        </div>
      </section>
    </main>
    <footer className="landing-footer">
      <div className="landing-container landing-footer-grid">
        <div><a href="#inicio"><MarcaEstabelecimento /></a><p>Cuidado nos detalhes. Tempo para você.</p></div>
        <nav aria-label="Navegação do rodapé"><h2>Navegação rápida</h2>
          <a href="#sobre">A barbearia</a>
          {secoesInicio.slice(1).map(([id, rotulo]) => <a href={`#${id}`} key={id}>{rotulo}</a>)}
        </nav>
        <div><h2>Horário de funcionamento</h2><HorariosInicio /><Link to="/agendar">Consultar horários</Link><Link to="/cliente/entrar">Portal do cliente</Link>
          <Link to="/login">Área dos funcionários</Link></div>
        <div><h2>Localização e contato</h2><a href="#localizacao">Consultar unidades e rotas</a>
          <ContatoInicio />
          {filial && <p>{filial.nome}{filial.endereco && <><br />{filial.endereco}</>}</p>}</div>
      </div>
      <div className="landing-container landing-credito">{estabelecimento.nome} · {software.nome}</div>
    </footer>
  </div>;
}
