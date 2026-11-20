import { useEffect, useState } from 'react';
import api from '../../services/api';
import { mensagemErro } from '../../services/erros';
import { dinheiro } from '../gerencial/formatacao';
import { descricaoEscopo } from '../../services/resumoCliente';
import type { ResumoCliente } from '../../services/resumoCliente';

const dataLocal = new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeZone: 'America/Recife' });

export function ResumoClientePerfil({ clienteId, administrador }: { clienteId: string; administrador: boolean }) {
  const [resumo, setResumo] = useState<ResumoCliente | null>(null);
  const [erro, setErro] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    const endpoint = administrador ? 'resumo-financeiro' : 'resumo';
    api.get<ResumoCliente>(`/clientes/${clienteId}/${endpoint}`, { signal: controller.signal }).then(({ data }) => {
      if (!controller.signal.aborted) setResumo(data);
    }).catch((falha) => {
      if (!controller.signal.aborted) setErro(mensagemErro(falha, 'Não foi possível consultar o resumo do cliente'));
    });
    return () => controller.abort();
  }, [clienteId, administrador]);
  return <section aria-label="Resumo do cliente">
    {erro ? <p role="alert">{erro}</p> : !resumo ? <p role="status">Carregando resumo...</p> : <>
      <p>{descricaoEscopo(resumo)}</p>
      <p>Atendimentos concluídos no escopo acima: {resumo.atendimentos_concluidos}</p>
      <details><summary>Detalhamento por filial</summary>
        <ul>{resumo.filiais.map((filial) => <li key={filial.filial_id}>
          {filial.filial_nome}: {filial.atendimentos_concluidos} atendimento(s) concluído(s)
          {administrador && resumo.financeiro_disponivel && filial.total_gasto != null && <> · Total pago líquido {dinheiro(filial.total_gasto)}</>}
        </li>)}</ul>
      </details>
      {administrador && resumo.financeiro_disponivel && <>
        <p><strong>Total pago líquido de estornos</strong> {dinheiro(resumo.total_gasto ?? null)}</p>
        <h3>Histórico financeiro</h3>
        {resumo.movimentacoes?.length ? <ul>{resumo.movimentacoes.map(m => <li key={m.comanda_id}>
          <div><strong>{dataLocal.format(new Date(m.ultima_movimentacao_em))} · {m.filial_nome}</strong>
          <p>{m.tipo === 'agendada' ? 'Atendimento agendado' : 'Venda avulsa'} · Pago {dinheiro(m.recebido)} · Estornado {dinheiro(m.estornado)}</p></div>
          <strong>Líquido {dinheiro(m.total_gasto)}</strong>
        </li>)}</ul> : <p>Nenhum pagamento registrado no escopo.</p>}
      </>}
    </>}
  </section>;
}
