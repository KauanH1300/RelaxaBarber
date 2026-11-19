import { useEffect, useState } from 'react';
import api from '../../services/api';
import { mensagemErro } from '../../services/erros';
import { useFilial } from '../../services/filialEstado';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { dinheiro, diaLocal } from './formatacao';
import './Gerencial.css';

type Valores = { bruto: string; faturado: string; recebido: string; estornos: string; recebido_liquido: string };
type Comissoes = { gerada: string; liberada: string; elegivel: string; paga: string };
type Resumo = {
  indicadores: Valores & { concluidos: number; clientes: number; cancelados: number; agendamentos: number;
    faltas: number; taxa_falta: string | null; taxa_cancelamento: string | null; ticket_medio: string | null; base_ticket: number };
  periodos: (Valores & { periodo: string })[];
  servicos: { id: string; nome: string; quantidade: number; faturado: string }[];
  profissionais: (Valores & Comissoes & { id: string | null; nome: string; concluidos: number })[];
  dias: Record<string, number>; horarios: Record<string, number>; comissoes: Comissoes;
};
type Evento = { id: string; tipo: string; referencia: string; registrado_em: string; autor: string | null; autor_cliente: boolean; motivo: string | null };
type Historico = { total: number; tamanho: number; itens: Evento[] };
type Profissional = { id: string; nome: string };
const tipos: Record<string, string> = {
  recebimento: 'Recebimento', estorno: 'Estorno de recebimento', fechamento: 'Fechamento financeiro',
  habilitacao: 'Habilitação financeira', beneficio: 'Benefício', inclusao_servico: 'Inclusão de serviço',
  alteracao_item: 'Alteração de item', cancelamento_comanda: 'Cancelamento de comanda',
  estoque: 'Movimento de estoque', repasse_fechamento: 'Fechamento de repasse',
  repasse_pagamento: 'Pagamento de repasse', repasse_estorno: 'Estorno de repasse',
  cancelamento_agendamento: 'Cancelamento de agenda', reagendamento: 'Reagendamento', nao_comparecimento: 'Não comparecimento',
};
const dias = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

function Movimento({ titulo, valores, rotulo }: { titulo: string; valores: Record<string, number>; rotulo: (key: string) => string }) {
  const maximo = Math.max(1, ...Object.values(valores));
  return <section className="gerencial-painel"><h2>{titulo}</h2>
    {Object.entries(valores).length ? <ul className="gerencial-barras">{Object.entries(valores).map(([chave, valor]) =>
      <li key={chave}><span>{rotulo(chave)}</span><meter max={maximo} value={valor} aria-label={rotulo(chave)} /><strong>{valor}</strong></li>
    )}</ul> : <p>Nenhum atendimento concluído no período.</p>}
  </section>;
}

export function Gerencial() {
  const { filialId } = useFilial();
  const [filtros, setFiltros] = useState(() => {
    const hoje = diaLocal();
    return { inicio: hoje.slice(0, 8) + '01', fim: hoje, profissional_id: '', busca: '', ordem: 'quantidade', ordem_equipe: 'faturado', granularidade: 'dia' };
  });
  const [form, setForm] = useState(filtros);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [equipe, setEquipe] = useState<Profissional[]>([]);
  const [historico, setHistorico] = useState<Historico | null>(null);
  const [tipo, setTipo] = useState('');
  const [pagina, setPagina] = useState(1);
  const [erro, setErro] = useState('');
  const [erroEquipe, setErroEquipe] = useState('');
  const [erroHistorico, setErroHistorico] = useState('');
  const [erroExportacao, setErroExportacao] = useState('');
  const [exportando, setExportando] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const { inicio, fim } = filtros;

  useEffect(() => {
    const controller = new AbortController();
    api.get<Profissional[]>('/usuarios/barbeiros', { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setEquipe(data); })
      .catch((e: unknown) => { if (!controller.signal.aborted) setErroEquipe(mensagemErro(e, 'Não foi possível carregar profissionais.')); });
    return () => controller.abort();
  }, [filialId, tentativa]);

  useEffect(() => {
    const controller = new AbortController();
    api.get<Resumo>('/gerencial/resumo', { params: { ...filtros, profissional_id: filtros.profissional_id || undefined, filial_id: filialId }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setResumo(data); })
      .catch((e: unknown) => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Não foi possível carregar o relatório.')); });
    return () => controller.abort();
  }, [filialId, filtros, tentativa]);

  useEffect(() => {
    const controller = new AbortController();
    api.get<Historico>('/gerencial/historico', { params: { inicio, fim, filial_id: filialId, tipo: tipo || undefined, pagina }, signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) setHistorico(data); })
      .catch((e: unknown) => { if (!controller.signal.aborted) setErroHistorico(mensagemErro(e, 'Não foi possível carregar o histórico.')); });
    return () => controller.abort();
  }, [filialId, inicio, fim, tipo, pagina, tentativa]);

  async function exportar() {
    const contexto = contextoAtual();
    setErroExportacao('');
    setExportando(true);
    try {
      const resposta = await api.get<Blob>('/gerencial/resumo', {
        params: { ...filtros, profissional_id: filtros.profissional_id || undefined, filial_id: filialId, formato: 'csv' },
        responseType: 'blob',
      });
      if (!contextoValido(contexto)) return;
      const url = URL.createObjectURL(resposta.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'relatorio-gerencial.csv';
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      if (contextoValido(contexto)) setErroExportacao('Não foi possível exportar o CSV.');
    } finally {
      setExportando(false);
    }
  }

  const valores = resumo?.indicadores;
  const percentual = (v: string | null) => v === null ? '—' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + '%';
  const indicadores = valores && [
    ['Faturamento', dinheiro(valores.faturado)], ['Recebido líquido', dinheiro(valores.recebido_liquido)],
    ['Estornos', dinheiro(valores.estornos)], ['Atendimentos concluídos', valores.concluidos],
    ['Clientes distintos', valores.clientes], ['Ticket médio por atendimento fechado', dinheiro(valores.ticket_medio)],
    ['Taxa de cancelamento', percentual(valores.taxa_cancelamento)], ['Taxa de faltas registradas', percentual(valores.taxa_falta)],
  ];

  function atualizarHistorico() { setHistorico(null); setErroHistorico(''); }
  function mudarPagina(n: number) { atualizarHistorico(); setPagina(n); }

  return <main className="gerencial">
    <header><h1>Gerencial</h1><p>Indicadores, faturamento e histórico da filial ativa.</p></header>
    <form className="gerencial-painel gerencial-filtros" onSubmit={(e) => {
      e.preventDefault();
      if (inicio !== form.inicio || fim !== form.fim) { atualizarHistorico(); setPagina(1); }
      setResumo(null); setErro(''); setErroExportacao(''); setFiltros({ ...form });
    }}>
      <label>Início<input type="date" required value={form.inicio} onChange={e => setForm({ ...form, inicio: e.target.value })} /></label>
      <label>Fim<input type="date" required min={form.inicio} value={form.fim} onChange={e => setForm({ ...form, fim: e.target.value })} /></label>
      <label>Profissional<select value={form.profissional_id} onChange={e => setForm({ ...form, profissional_id: e.target.value })}>
        <option value="">Todos</option>{equipe.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}
      </select></label>
      <label>Agrupar por<select value={form.granularidade} onChange={e => setForm({ ...form, granularidade: e.target.value })}>
        <option value="dia">Dia</option><option value="semana">Semana</option><option value="mes">Mês</option>
      </select></label>
      <label>Buscar serviço<input type="search" maxLength={100} value={form.busca} onChange={e => setForm({ ...form, busca: e.target.value })} /></label>
      <label>Ordenar serviços<select value={form.ordem} onChange={e => setForm({ ...form, ordem: e.target.value })}>
        <option value="quantidade">Quantidade</option><option value="faturado">Faturamento</option>
      </select></label>
      <label>Ordenar desempenho<select value={form.ordem_equipe} onChange={e => setForm({ ...form, ordem_equipe: e.target.value })}>
        <option value="faturado">Faturamento</option><option value="concluidos">Atendimentos</option>
        <option value="recebido_liquido">Caixa líquido</option><option value="liberada">Comissão liberada</option>
      </select></label>
      <button>Aplicar filtros</button>
    </form>
    {erroEquipe && <p role="alert">{erroEquipe}</p>}
    {(erro || erroEquipe || erroHistorico) && <button onClick={() => {
      setResumo(null); setErro(''); setErroEquipe(''); atualizarHistorico(); setTentativa(n => n + 1);
    }}>Tentar novamente</button>}
    {erro ? <p role="alert">{erro}</p> : !resumo && <p role="status">Carregando relatório…</p>}
    {resumo && indicadores && <>
      <button disabled={exportando} onClick={() => void exportar()}>{exportando ? 'Exportando…' : 'Exportar CSV'}</button>
      {erroExportacao && <p role="alert">{erroExportacao}</p>}
      <dl className="gerencial-indicadores">{indicadores.map(([nome, valor]) => <div key={nome}><dt>{nome}</dt><dd>{valor}</dd></div>)}</dl>
      <p>As taxas usam todos os agendamentos da seleção. O ticket médio usa {valores?.base_ticket ?? 0} atendimento(s) com fechamento financeiro no período.</p>
      <div className="gerencial-graficos">
        <Movimento titulo="Atendimentos por dia da semana" valores={resumo.dias} rotulo={d => dias[Number(d)]} />
        <Movimento titulo="Atendimentos por horário" valores={resumo.horarios} rotulo={h => h.padStart(2, '0') + ':00'} />
      </div>
      <section className="gerencial-painel"><h2>Faturamento e caixa</h2><p>Faturamento pela data do fechamento. Caixa pelas datas efetivas de recebimentos e estornos.</p>
        {resumo.periodos.length ? <table><thead><tr><th>Início do grupo</th><th>Bruto</th><th>Faturado</th><th>Recebido</th><th>Estornos</th><th>Recebido líquido</th></tr></thead>
          <tbody>{resumo.periodos.map(p => <tr key={p.periodo}><td>{p.periodo.split('-').reverse().join('/')}</td><td>{dinheiro(p.bruto)}</td><td>{dinheiro(p.faturado)}</td><td>{dinheiro(p.recebido)}</td><td>{dinheiro(p.estornos)}</td><td>{dinheiro(p.recebido_liquido)}</td></tr>)}</tbody></table> : <p>Sem movimentação no período.</p>}
      </section>
      <section className="gerencial-painel"><h2>Ranking de serviços faturados</h2>
        {resumo.servicos.length ? <table><thead><tr><th>Serviço</th><th>Quantidade</th><th>Faturamento</th></tr></thead>
          <tbody>{resumo.servicos.map(s => <tr key={s.id}><td>{s.nome}</td><td>{s.quantidade}</td><td>{dinheiro(s.faturado)}</td></tr>)}</tbody></table> : <p>Nenhum serviço encontrado.</p>}
      </section>
      <section className="gerencial-painel"><h2>Comissões</h2><p>Posição atual das comissões com origem no período. Pago líquido de estornos de repasse.</p>
        <dl className="gerencial-indicadores">{Object.entries({ Geradas: resumo.comissoes.gerada, Liberadas: resumo.comissoes.liberada, Elegíveis: resumo.comissoes.elegivel, Pagas: resumo.comissoes.paga }).map(([nome, valor]) => <div key={nome}><dt>{nome}</dt><dd>{dinheiro(valor)}</dd></div>)}</dl>
        <h3>Desempenho por profissional</h3>
        <p>Faturamento e caixa seguem o profissional da comanda. Vendas avulsas sem profissional aparecem em linha própria.</p>
        {resumo.profissionais.length ? <table><thead><tr><th>Profissional</th><th>Atendimentos</th><th>Faturado</th><th>Caixa líquido</th><th>Gerada</th><th>Liberada</th><th>Elegível</th><th>Paga</th></tr></thead>
          <tbody>{resumo.profissionais.map(p => <tr key={p.id ?? 'sem-profissional'}><td>{p.nome}</td><td>{p.concluidos}</td><td>{dinheiro(p.faturado)}</td><td>{dinheiro(p.recebido_liquido)}</td><td>{dinheiro(p.gerada)}</td><td>{dinheiro(p.liberada)}</td><td>{dinheiro(p.elegivel)}</td><td>{dinheiro(p.paga)}</td></tr>)}</tbody></table> : <p>Nenhum resultado no período.</p>}
      </section>
    </>}
    <section className="gerencial-painel"><h2>Histórico da filial</h2><p>Eventos pela data de registro, para todos os profissionais.</p>
      <label>Tipo de evento<select value={tipo} onChange={e => { atualizarHistorico(); setPagina(1); setTipo(e.target.value); }}>
        <option value="">Todos</option>{Object.entries(tipos).map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}
      </select></label>
      {erroHistorico ? <p role="alert">{erroHistorico}</p> : !historico ? <p role="status">Carregando histórico…</p> : <>
        {historico.itens.length ? <table><thead><tr><th>Registro</th><th>Evento</th><th>Referência</th><th>Autor</th><th>Motivo</th></tr></thead>
          <tbody>{historico.itens.map(h => <tr key={h.tipo + h.id}><td>{new Date(h.registrado_em).toLocaleString('pt-BR', { timeZone: 'America/Recife' })}</td><td>{tipos[h.tipo]}</td><td>{h.referencia}</td><td>{h.autor ?? '—'}{h.autor_cliente ? ' (cliente)' : ''}</td><td>{h.motivo ?? '—'}</td></tr>)}</tbody></table> : <p>Nenhum evento nesta página.</p>}
        <p>Página {pagina} de {Math.max(1, Math.ceil(historico.total / historico.tamanho))}</p>
        <button disabled={pagina === 1} onClick={() => mudarPagina(pagina - 1)}>Anterior</button>
        <button disabled={pagina * historico.tamanho >= historico.total} onClick={() => mudarPagina(pagina + 1)}>Próxima</button>
      </>}
    </section>
  </main>;
}

