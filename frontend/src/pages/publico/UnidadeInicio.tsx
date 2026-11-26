import { useEffect, useState } from 'react';
import { ContatoInicio, HorariosInicio } from './ContatoInicio';
import { Link } from 'react-router-dom';
import { Icone } from '../../components/Icone';
import rodrigo from '../../assets/rodrigo_relaxa.png';
import higor from '../../assets/higor_rodrigo.png';
import { filiaisPublicas, servicosDaFilial } from '../../services/agendamentoPublico';
import type { FilialPublica } from '../../services/agendamentoPublico';
import type { Servico } from '../../services/servico';
import { useAgendaPublica } from './useAgendaPublica';

type Estado = 'carregando' | 'pronto' | 'erro';
const fotos = new Map([['rodrigo relaxa', rodrigo], ['higor rodrigo', higor]]);

export function useFiliaisInicio() {
  const [filiais, setFiliais] = useState<FilialPublica[]>([]);
  const [estado, setEstado] = useState<Estado>('carregando');
  useEffect(() => {
    const controller = new AbortController();
    filiaisPublicas(controller.signal).then(itens => {
      if (controller.signal.aborted) return;
      setFiliais(itens);
      setEstado('pronto');
    }).catch(() => {
      if (!controller.signal.aborted) setEstado('erro');
    });
    return () => controller.abort();
  }, []);
  return { filiais, estado };
}

function EquipeDaUnidade({ id }: { id: string }) {
  const [catalogo, setCatalogo] = useState<Servico[] | null>(null);
  const [erro, setErro] = useState(false);
  const [servicoId, setServicoId] = useState('');
  const servico = catalogo?.find(item => item.id === servicoId) ?? catalogo?.[0];
  const { equipe } = useAgendaPublica(id, servico?.id ?? '', '', '');

  useEffect(() => {
    const controller = new AbortController();
    servicosDaFilial(id, controller.signal).then(itens => {
      if (!controller.signal.aborted) setCatalogo(itens);
    }).catch(() => {
      if (!controller.signal.aborted) setErro(true);
    });
    return () => controller.abort();
  }, [id]);

  return <>
    {catalogo && catalogo.length > 1 && <label className="landing-campo">
      Serviço <select value={servico?.id ?? ''} onChange={evento => setServicoId(evento.target.value)}>
        {catalogo.map(item => <option key={item.id} value={item.id}>{item.nome}</option>)}
      </select>
    </label>}
    {erro || equipe?.erro ? <p role="status">Não foi possível consultar os profissionais no momento.</p>
      : !catalogo || (servico && !equipe) ? <p role="status">Carregando profissionais…</p>
      : !equipe?.itens.length && <p role="status">Nenhum profissional disponível para esta seleção.</p>}
    {equipe && !equipe.erro && <div className="landing-equipe">
      {equipe.itens.map(profissional => {
        const foto = fotos.get(profissional.nome.trim().toLowerCase());
        return <article className="landing-card landing-profissional" key={profissional.id}>
          {foto ? <img src={foto} alt="" loading="lazy" /> : <div className="landing-sem-foto"><Icone nome="content_cut" /></div>}
          <div><h3>{profissional.nome}</h3>
            <Link className="landing-btn landing-btn-menor" to={`/agendar?servico=${encodeURIComponent(servico?.id ?? '')}`}
              aria-label={`Agendar ${servico?.nome ?? 'um serviço'} e consultar profissionais`}>Consultar agendamento</Link>
          </div>
        </article>;
      })}
    </div>}
  </>;
}

export function UnidadeInicio({ filial, filiais, estado, selecionar }: {
  filial?: FilialPublica;
  filiais: FilialPublica[];
  estado: Estado;
  selecionar: (id: string) => void;
}) {
  const endereco = filial?.endereco?.trim();
  const destino = endereco ? encodeURIComponent(endereco) : '';
  const rota = destino ? `https://www.google.com/maps/dir/?api=1&destination=${destino}` : '';
  return <>
    <section tabIndex={-1} id="equipe" className="landing-secao" aria-labelledby="landing-equipe">
      <div className="landing-container">
        <div className="landing-intro"><p className="landing-selo">Nossa equipe</p>
          <h2 id="landing-equipe">Conheça nossos profissionais</h2>
          <p>Consulte os profissionais que atendem na unidade para o serviço de sua preferência.</p>
        </div>
        {filiais.length > 1 && <label className="landing-campo">
          Unidade <select value={filial?.id ?? ''} onChange={evento => selecionar(evento.target.value)}>
            {filiais.map(item => <option key={item.id} value={item.id}>{item.nome}</option>)}
          </select>
        </label>}
        {filial ? <EquipeDaUnidade id={filial.id} key={filial.id} />
          : <p role="status">{estado === 'carregando' ? 'Carregando profissionais…'
            : estado === 'erro' ? 'Não foi possível consultar os profissionais no momento.'
            : 'Nenhuma unidade disponível para consultar a equipe.'}</p>}
      </div>
    </section>

    <section tabIndex={-1} id="localizacao" className="landing-secao landing-escura" aria-labelledby="landing-localizacao">
      <div className="landing-container landing-local">
        <div>
          <p className="landing-selo">Localização e contato</p>
          <h2 id="landing-localizacao">Venha nos conhecer</h2>
          <p>Encontre a barbearia e consulte os horários disponíveis para seu atendimento.</p>
          {filiais.length > 1 && <label className="landing-campo">
            Unidade <select value={filial?.id ?? ''} onChange={evento => selecionar(evento.target.value)}>
              {filiais.map(item => <option key={item.id} value={item.id}>{item.nome}</option>)}
            </select>
          </label>}
          <div className="landing-local-cards">
            <article className="landing-card"><h3>Horário de funcionamento</h3>
              <HorariosInicio />
            </article>
            <article className="landing-card"><h3>Contato</h3>
              <ContatoInicio />
            </article>
          </div>
          {filial && <address><strong>{filial.nome}</strong>{endereco && <span>{endereco}</span>}</address>}
        </div>
        {rota ? <figure className="landing-mapa">
          <iframe src={`https://maps.google.com/maps?q=${destino}&output=embed`} loading="lazy"
            title={`Mapa da unidade ${filial?.nome}`} referrerPolicy="no-referrer" />
          <figcaption><span>{filial?.nome}</span>
            <a className="landing-btn landing-btn-ouro" href={rota}>Abrir rota</a>
          </figcaption>
        </figure> : <div className="landing-mapa landing-mapa-estado" role="status">
          <span className="landing-icone" aria-hidden="true">⌖</span>
          <p>{estado === 'carregando' ? 'Carregando localização…' : 'Endereço indisponível no momento.'}</p>
        </div>}
      </div>
    </section>
  </>;
}
