import { useEffect, useRef, useState } from 'react';
import { Icone } from '../../components/Icone';
import type { FilialPublica } from '../../services/agendamentoPublico';
import { consultarVitrine, type ProdutoVitrine } from '../../services/vitrinePublica';
import { precoPublico } from './useCatalogoPublico';

function FotoProduto({ produto }: { produto: ProdutoVitrine }) {
  const [falhou, setFalhou] = useState(false);
  return <div className="landing-produto-foto">
    {produto.foto_url && !falhou
      ? <img src={produto.foto_url} alt="" loading="lazy" onError={() => setFalhou(true)} />
      : <span>Sem foto</span>}
  </div>;
}

function ProdutosDaUnidade({ filialId }: { filialId: string }) {
  const [produtos, setProdutos] = useState<ProdutoVitrine[] | null>(null);
  const [completa, setCompleta] = useState(false);
  const [proxima, setProxima] = useState<number | null>(null);
  const [carregandoMais, setCarregandoMais] = useState(false);
  const [erroMais, setErroMais] = useState(false);
  const consultaMais = useRef<AbortController | null>(null);
  const [erro, setErro] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    consultarVitrine(filialId, 1, controller.signal).then(pagina => {
      if (!controller.signal.aborted) {
        setProdutos(pagina.produtos);
        setProxima(pagina.proxima_pagina);
      }
    }).catch(() => {
      if (!controller.signal.aborted) setErro(true);
    });
    return () => {
      controller.abort();
      consultaMais.current?.abort();
    };
  }, [filialId, tentativa]);

  if (erro) return <div>
    <p role="status">Não foi possível carregar os produtos.</p>
    <button className="landing-btn mt-3" type="button" onClick={() => {
      setErro(false);
      setTentativa(atual => atual + 1);
    }}>Tentar novamente</button>
  </div>;
  if (!produtos) return <p role="status">Carregando produtos…</p>;
  if (!produtos.length) return <p role="status">Nenhum produto na vitrine desta unidade no momento.</p>;

  async function carregarMais() {
    if (!proxima || consultaMais.current) return;
    const controller = new AbortController();
    consultaMais.current = controller;
    setCarregandoMais(true);
    setErroMais(false);
    try {
      const pagina = await consultarVitrine(filialId, proxima, controller.signal);
      if (controller.signal.aborted) return;
      setProdutos(atuais => [...(atuais ?? []), ...pagina.produtos]);
      setProxima(pagina.proxima_pagina);
    } catch {
      if (!controller.signal.aborted) setErroMais(true);
    } finally {
      consultaMais.current = null;
      if (!controller.signal.aborted) setCarregandoMais(false);
    }
  }

  return <>
    <ul id="landing-lista-produtos" className="landing-produtos">
      {(completa ? produtos : produtos.slice(0, 3)).map((produto, indice) => <li className="landing-card landing-produto" key={indice}>
        <FotoProduto produto={produto} />
        <div className="landing-produto-detalhes">
          <h3>{produto.nome}</h3>
          <strong className="landing-ouro">{precoPublico(Number(produto.preco))}</strong>
          {produto.descricao && <p>{produto.descricao}</p>}
          <span className="landing-produto-status">
            {produto.disponivel ? 'Disponível no balcão' : 'Indisponível no momento'}
          </span>
        </div>
      </li>)}
    </ul>
    {(produtos.length > 3 || proxima !== null) && <div className="landing-acoes">
      <button className="landing-btn landing-ouro" type="button" aria-expanded={completa}
        aria-controls="landing-lista-produtos" onClick={() => {
          setCompleta(!completa);
          if (!completa && produtos.length <= 3 && proxima) void carregarMais();
        }}><Icone nome="grid_view" /> {completa ? 'Mostrar menos produtos' : 'Ver vitrine completa'}</button>
      {completa && proxima !== null && <button className="landing-btn" type="button"
        disabled={carregandoMais} onClick={() => void carregarMais()}>
        {carregandoMais ? 'Carregando produtos…' : 'Carregar mais produtos'}
      </button>}
    </div>}
    {completa && erroMais && <p role="status" className="mt-3 text-center">Não foi possível carregar mais produtos. Tente novamente.</p>}
  </>;
}

export function VitrineInicio({ filial, filiais, estado, selecionar }: {
  filial?: FilialPublica;
  filiais: FilialPublica[];
  estado: 'carregando' | 'pronto' | 'erro';
  selecionar: (id: string) => void;
}) {
  return <section tabIndex={-1} id="vitrine" className="landing-secao landing-vitrine" aria-labelledby="landing-vitrine">
    <div className="landing-container">
      <div className="landing-intro">
        <p className="landing-selo">Vitrine de cuidados</p>
        <h2 id="landing-vitrine">Produtos selecionados para o seu cuidado diário</h2>
        <p>Conheça os produtos vendidos na barbearia e consulte preços e disponibilidade por unidade.</p>
      </div>
      {filiais.length > 1 && <label className="landing-campo">
        Unidade <select value={filial?.id ?? ''} onChange={evento => selecionar(evento.target.value)}>
          {filiais.map(item => <option key={item.id} value={item.id}>{item.nome}</option>)}
        </select>
      </label>}
      {filial ? <ProdutosDaUnidade key={filial.id} filialId={filial.id} />
        : <p role="status">{estado === 'carregando' ? 'Carregando vitrine…'
          : estado === 'erro' ? 'Não foi possível consultar as unidades.'
          : 'Nenhuma unidade com vitrine disponível.'}</p>}
    </div>
  </section>;
}
