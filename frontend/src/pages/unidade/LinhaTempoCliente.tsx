import { useEffect, useState } from 'react';
import api from '../../services/api';
import { mensagemErro } from '../../services/erros';
import { dinheiro } from '../gerencial/formatacao';

type Item = { nome: string; quantidade: number };
type Insumo = { nome: string; unidade: string; quantidade: string };
interface Atendimento {
  id: string; data: string; hora_inicio: string; profissional: string;
  status: 'concluido' | 'cancelado' | 'nao_compareceu';
  observacoes: string | null; servicos: Item[]; produtos: Item[]; insumos: Insumo[];
  total_pago_liquido?: string;
}
interface Pagina { atendimentos: Atendimento[]; proxima_pagina: number | null }

const status = { concluido: 'Concluído', cancelado: 'Cancelado', nao_compareceu: 'Não compareceu' };
const quantidade = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 });

export function LinhaTempoCliente({ clienteId, filialId }: { clienteId: string; filialId: string }) {
  const [pagina, setPagina] = useState(1);
  const [incluir, setIncluir] = useState(false);
  const [resultado, setResultado] = useState<Pagina | null>(null);
  const [erro, setErro] = useState('');
  const [tentativa, setTentativa] = useState(0);

  useEffect(() => {
    const c = new AbortController();
    api.get<Pagina>(`/clientes/${clienteId}/atendimentos`, {
      params: { filial_id: filialId, pagina, incluir_ocorrencias: incluir }, signal: c.signal,
    }).then(({ data }) => { if (!c.signal.aborted) setResultado(data); })
      .catch(falha => { if (!c.signal.aborted) setErro(mensagemErro(falha, 'Não foi possível carregar os atendimentos.')); });
    return () => c.abort();
  }, [clienteId, filialId, pagina, incluir, tentativa]);

  function mudar(nova: number) {
    setResultado(null); setErro(''); setPagina(nova);
  }

  return <section aria-label="Linha do tempo de atendimentos" aria-busy={!resultado && !erro}>
    <h3>Linha do tempo de atendimentos</h3>
    <label><input type="checkbox" checked={incluir} onChange={e => {
      setIncluir(e.target.checked); mudar(1);
    }} /> Incluir cancelados e faltas</label>
    {erro ? <><p role="alert">{erro}</p><button type="button" onClick={() => {
      setErro(''); setTentativa(n => n + 1);
    }}>Tentar novamente</button></> : !resultado ? <p role="status">Carregando atendimentos…</p> : <>
      {!resultado.atendimentos.length && <p>Nenhum atendimento encontrado nesta filial para o filtro selecionado.</p>}
      <ol className="cliente-linha-tempo">{resultado.atendimentos.map(a => <li key={a.id}>
        <article>
          <h4>{a.data.split('-').reverse().join('/')} às {a.hora_inicio.slice(0, 5)} · {a.profissional}</h4>
          <p>{status[a.status]}</p>
          {!!a.servicos.length && <p><strong>{a.status === 'concluido' ? 'Serviços' : 'Serviços agendados'}</strong> {a.servicos.map(s => `${s.quantidade} × ${s.nome}`).join(', ')}</p>}
          {!!a.produtos.length && <p><strong>Produtos adquiridos</strong> {a.produtos.map(p => `${p.quantidade} × ${p.nome}`).join(', ')}</p>}
          {!!a.insumos.length && <p><strong>Insumos consumidos</strong> {a.insumos.map(i => `${i.nome} (${quantidade.format(Number(i.quantidade))} ${i.unidade})`).join(', ')}</p>}
          {a.observacoes && <p className="cliente-preferencias"><strong>Observações</strong> {a.observacoes}</p>}
          {a.total_pago_liquido != null && <p><strong>Total pago líquido de estornos</strong> {dinheiro(a.total_pago_liquido)}</p>}
        </article>
      </li>)}</ol>
      {(pagina > 1 || resultado.proxima_pagina) && <nav aria-label="Páginas dos atendimentos" className="clientes-acoes">
        <button type="button" disabled={pagina === 1} onClick={() => mudar(pagina - 1)}>Anterior</button>
        <span>Página {pagina}</span>
        <button type="button" disabled={!resultado.proxima_pagina} onClick={() => mudar(pagina + 1)}>Próxima</button>
      </nav>}
    </>}
  </section>;
}
