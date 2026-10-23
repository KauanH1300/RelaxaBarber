import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import api from '../../services/api';
import { useUsuario } from '../../services/usuario';
import type { FiltrosComanda, PainelComandas, PessoaComanda, StatusComanda } from '../../services/comandas';
import { consultarComandas, diaRecife, erroConsultaComanda, intervaloPagina, statusComanda } from '../../services/comandas';
import { CardComanda, IconeComanda, Indicadores } from './ComponentesComanda';
import { DetalheComanda } from './DetalheComanda';
import './Comandas.css';

function filtrosIniciais(): FiltrosComanda {
  const hoje = diaRecife();
  return { busca: '', profissional_id: '', data_inicio: hoje, data_fim: hoje, status: '' };
}
export function Comandas() {
  const usuario = useUsuario();
  const [filtros, setFiltros] = useState(filtrosIniciais);
  const [formulario, setFormulario] = useState(filtros);
  const [pagina, setPagina] = useState(1);
  const [revisao, setRevisao] = useState(0);
  const [dados, setDados] = useState<PainelComandas | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState('');
  const [profissionais, setProfissionais] = useState<PessoaComanda[]>([]);
  const [erroProfissionais, setErroProfissionais] = useState('');
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [visualizacao, setVisualizacao] = useState<'grade' | 'lista'>('grade');
  useEffect(() => {
    const controller = new AbortController();
    consultarComandas(filtros, pagina, controller.signal).then((resposta) => {
      if (!controller.signal.aborted) { setDados(resposta); setErro(''); }
    }).catch((falha: unknown) => {
      if (!controller.signal.aborted) { setDados(null); setErro(erroConsultaComanda(falha)); }
    }).finally(() => { if (!controller.signal.aborted) setCarregando(false); });
    return () => controller.abort();
  }, [filtros, pagina, revisao]);
  useEffect(() => {
    const controller = new AbortController();
    api.get<PessoaComanda[]>('/usuarios/barbeiros', { signal: controller.signal }).then(({ data }) => {
      if (!controller.signal.aborted) { setProfissionais(data); setErroProfissionais(''); }
    }).catch(() => { if (!controller.signal.aborted) { setProfissionais([]); setErroProfissionais('Não foi possível carregar o filtro de profissionais. Use Atualizar para tentar novamente.'); } });
    return () => controller.abort();
  }, [revisao]);
  function aplicar(event: FormEvent) {
    event.preventDefault();
    setCarregando(true); setErro(''); setPagina(1); setFiltros({ ...formulario, status: filtros.status });
  }
  function trocarStatus(status: StatusComanda | '') {
    setCarregando(true); setPagina(1); setFiltros((atual) => ({ ...atual, status }));
  }
  function atualizar() { setCarregando(true); setRevisao((n) => n + 1); }
  function mudarPagina(numero: number) { setCarregando(true); setPagina(numero); }
  const resultado = carregando ? null : dados;
  const paginas = dados ? Math.max(1, Math.ceil(dados.total / dados.tamanho)) : 1;
  const estados = Object.keys(statusComanda) as StatusComanda[];
  return <section className="comandas-pagina" aria-labelledby="comandas-titulo">
    <div className="comandas-caminho">Operação <span>/</span><strong>Comandas</strong></div>
    <header className="comandas-cabecalho"><div><h1 id="comandas-titulo">Comandas &amp; Consumo</h1>
      <p>Acompanhe os itens e o andamento dos atendimentos da unidade.</p></div>
      <button type="button" className="comandas-botao-dourado" onClick={atualizar} disabled={carregando}><IconeComanda nome="refresh" />Atualizar</button></header>
    <Indicadores dados={resultado?.indicadores ?? null} carregando={carregando} />
    <p className="comandas-escopo">Indicadores de todo o resultado da pesquisa, profissional e período, independentemente da página ou aba de status.</p>
    <div className="comandas-filtros-painel"><form onSubmit={aplicar} className="comandas-filtros">
      <label className="comandas-busca">Pesquisar cliente ou identificação
        <div><IconeComanda nome="search" /><input type="search" maxLength={100} placeholder="Nome do cliente ou parte do UUID" value={formulario.busca} onChange={(e) => setFormulario({ ...formulario, busca: e.target.value })} /></div></label>
      <label>Profissional<select value={formulario.profissional_id} disabled={!!erroProfissionais} onChange={(e) => setFormulario({ ...formulario, profissional_id: e.target.value })}>
        <option value="">{usuario.perfil === 'barbeiro' ? 'Minha agenda' : 'Todos os autorizados'}</option>{profissionais.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}</select></label>
      <label>Atendimento de<input aria-label="Data inicial do atendimento" type="date" value={formulario.data_inicio} max={formulario.data_fim || undefined} onChange={(e) => setFormulario({ ...formulario, data_inicio: e.target.value })} /></label>
      <label>Até<input aria-label="Data final do atendimento" type="date" value={formulario.data_fim} min={formulario.data_inicio || undefined} onChange={(e) => setFormulario({ ...formulario, data_fim: e.target.value })} /></label>
      <button type="submit" className="comandas-botao-secundario">Aplicar filtros</button>
    </form>{erroProfissionais && <p role="alert" className="comandas-erro-filtro">{erroProfissionais}</p>}
    <div className="comandas-filtros-rodape"><div className="comandas-abas" role="group" aria-label="Filtrar por status da comanda">
      <button type="button" aria-pressed={!filtros.status} onClick={() => trocarStatus('')}>Todas</button>
      {estados.map((status) => <button type="button" key={status} aria-pressed={filtros.status === status} onClick={() => trocarStatus(status)}>
        {statusComanda[status]}{resultado && <span>{resultado.indicadores.contagens[status]}</span>}</button>)}
    </div><div className="comandas-visualizacao" role="group" aria-label="Visualização">
      <button type="button" aria-label="Visualizar em grade" aria-pressed={visualizacao === 'grade'} onClick={() => setVisualizacao('grade')}><IconeComanda nome="grid_view" /></button>
      <button type="button" aria-label="Visualizar em lista" aria-pressed={visualizacao === 'lista'} onClick={() => setVisualizacao('lista')}><IconeComanda nome="view_list" /></button>
    </div></div></div>
    <div aria-busy={carregando} className="comandas-resultados">
      {carregando ? <div className="comandas-estado"><span className="comandas-spinner" aria-hidden="true" /><p role="status">Carregando comandas…</p></div>
        : erro ? <div className="comandas-estado"><IconeComanda nome="cloud_off" /><h2>Não foi possível consultar</h2><p role="alert">{erro}</p><button onClick={atualizar}>Tentar novamente</button></div>
        : resultado?.itens.length ? <div className={`comandas-grid comandas-${visualizacao}`}>{resultado.itens.map((comanda) => <CardComanda key={comanda.id} comanda={comanda} aoDetalhar={setSelecionada} />)}</div>
        : <div className="comandas-estado"><IconeComanda nome="receipt_long" /><h2>Nenhuma comanda encontrada</h2><p>Experimente outro período, profissional ou pesquisa.</p>{pagina > 1 && <button onClick={() => mudarPagina(1)}>Voltar à primeira página</button>}</div>}
    </div>
    {resultado && <nav className="comandas-paginacao" aria-label="Paginação das comandas"><p role="status">Exibindo <strong>{intervaloPagina(pagina, resultado.tamanho, resultado.total)}</strong> de <strong>{resultado.total}</strong> comandas</p>
      <div><button type="button" disabled={pagina <= 1} onClick={() => mudarPagina(pagina - 1)}><IconeComanda nome="chevron_left" />Anterior</button>
        <span>Página {pagina} de {paginas}</span><button type="button" disabled={pagina >= paginas} onClick={() => mudarPagina(pagina + 1)}>Próxima<IconeComanda nome="chevron_right" /></button></div></nav>}
    <aside className="comandas-nota"><IconeComanda nome="info" /><p>Consulta operacional. Comanda fechada não significa pagamento recebido. Pagamentos e edição de itens estarão disponíveis em etapas futuras.</p></aside>
    {selecionada && <DetalheComanda key={selecionada} id={selecionada} aoFechar={() => setSelecionada(null)} />}
  </section>;
}
