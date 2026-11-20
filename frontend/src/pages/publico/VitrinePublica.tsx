import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { CabecalhoPublico, RodapePublico } from './ComponentesPublicos';
import { apiPublica, filiaisPublicas } from '../../services/agendamentoPublico';
import type { FilialPublica } from '../../services/agendamentoPublico';
import { precoPublico } from './useCatalogoPublico';
import './publico.css';
import './VitrinePublica.css';

interface Produto {
  nome: string; descricao: string | null; foto_url: string | null; preco: string; disponivel: boolean;
}
interface Pagina { produtos: Produto[]; proxima_pagina: number | null }

function Foto({ produto }: { produto: Produto }) {
  const [falhou, setFalhou] = useState(false);
  return produto.foto_url && !falhou
    ? <img className="vitrine-foto" src={produto.foto_url} alt={produto.nome} loading="lazy" onError={() => setFalhou(true)} />
    : <div className="vitrine-foto vitrine-placeholder">Sem foto</div>;
}

export function VitrinePublica() {
  const [params, selecionar] = useSearchParams();
  const [filiais, setFiliais] = useState<FilialPublica[] | null>(null);
  const [erroFiliais, setErroFiliais] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const pedida = params.get('filial_id');
  const filial = filiais?.find(f => f.id === pedida) ?? (filiais?.length === 1 ? filiais[0] : null);
  useEffect(() => {
    const c = new AbortController();
    filiaisPublicas(c.signal).then(rows => { if (!c.signal.aborted) setFiliais(rows); })
      .catch(() => { if (!c.signal.aborted) setErroFiliais(true); });
    return () => c.abort();
  }, [tentativa]);

  return <div className="publico">
    <CabecalhoPublico />
    <main className="publico-agenda-main vitrine">
      <Link className="publico-text-link" to="/agendar">Voltar ao agendamento</Link>
      <h1>Vitrine de produtos</h1>
      <p>Consulte produtos e preços de balcão.</p>
      {erroFiliais ? <><p role="alert">Não foi possível carregar as filiais.</p>
        <button type="button" onClick={() => { setErroFiliais(false); setTentativa(n => n + 1); }}>Tentar novamente</button></>
        : !filiais ? <p role="status">Carregando filiais…</p>
        : !filiais.length ? <p>Nenhuma filial com vitrine disponível.</p>
        : <label>Filial<select value={filial?.id ?? ''} onChange={e => selecionar({ filial_id: e.target.value })}>
          <option value="" disabled>Selecione uma filial</option>
          {filiais.map(f => <option key={f.id} value={f.id}>{f.nome}</option>)}
        </select></label>}
      {filial && <Catalogo key={filial.id} filial={filial.id} />}
    </main>
    <RodapePublico />
  </div>;
}

function Catalogo({ filial }: { filial: string }) {
  const [pagina, setPagina] = useState(1);
  const [resultado, setResultado] = useState<Pagina | null>(null);
  const [erro, setErro] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    apiPublica.get<Pagina>(`/publico/filiais/${encodeURIComponent(filial)}/produtos`, { params: { pagina }, signal: c.signal })
      .then(({ data }) => { if (!c.signal.aborted) setResultado(data); })
      .catch(() => { if (!c.signal.aborted) setErro(true); });
    return () => c.abort();
  }, [filial, pagina, tentativa]);

  function mudar(n: number) {
    setResultado(null); setErro(false); setPagina(n);
  }

  if (erro) return <><p role="alert">Não foi possível carregar os produtos.</p>
    <button type="button" onClick={() => { setErro(false); setTentativa(n => n + 1); }}>Tentar novamente</button></>;
  if (!resultado) return <p role="status">Carregando produtos…</p>;
  return <>
    {resultado.produtos.length ? <ul className="vitrine-grade">{resultado.produtos.map((p, i) =>
      <li key={pagina + ':' + i}>
        <Foto produto={p} />
        <h2>{p.nome}</h2>{p.descricao && <p>{p.descricao}</p>}
        <strong>{precoPublico(Number(p.preco))}</strong>
        <span className={p.disponivel ? 'vitrine-disponivel' : ''}>{p.disponivel ? 'Disponível' : 'Indisponível'}</span>
      </li>)}</ul> : <p>Nenhum produto listado nesta página.</p>}
    {(pagina > 1 || resultado.proxima_pagina) && <nav className="vitrine-paginacao" aria-label="Páginas da vitrine">
      <button type="button" disabled={pagina === 1} onClick={() => mudar(pagina - 1)}>Anterior</button>
      <span>Página {pagina}</span>
      <button type="button" disabled={!resultado.proxima_pagina} onClick={() => mudar(pagina + 1)}>Próxima</button>
    </nav>}
  </>;
}
