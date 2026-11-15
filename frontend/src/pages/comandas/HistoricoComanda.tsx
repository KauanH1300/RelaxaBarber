import { instanteRecife, moeda } from '../../services/comandas';
import { formasPagamento, pagamentosComEstornos } from '../../services/financeiro';
import type { ResumoFinanceiro } from '../../services/financeiro';

export function HistoricoComanda({ resumo }: { resumo: ResumoFinanceiro }) {
  if (resumo.situacao === 'nao_verificado') return <section aria-label="Histórico financeiro"><h4>Histórico financeiro não verificado</h4><p>A ausência de registros verificados não comprova dívida ou pagamento.</p></section>;
  const pagamentos = pagamentosComEstornos(resumo.historico);
  return <section aria-label="Histórico financeiro"><h4>Histórico financeiro</h4>
    <p>Pagamentos em ordem de registro, com seus estornos associados. Datas em America/Recife.</p>
    {!pagamentos.length && <p>Nenhum pagamento registrado.</p>}
    <ol className="financeiro-historico">{pagamentos.map((pagamento) => <li key={pagamento.id}>
      <strong>Pagamento · {moeda(pagamento.valor)} · {formasPagamento[pagamento.forma]}</strong>
      <span>Recebido em {instanteRecife(pagamento.recebido_em)}</span>
      <span>Registrado em {instanteRecife(pagamento.registrado_em)}</span>
      <span>Estornado: {moeda(pagamento.estornado)} · Líquido: {moeda(pagamento.liquido)}</span>
      <details><summary>Identificação do pagamento</summary><span>{pagamento.id}</span></details>
      {pagamento.estornos.length > 0 && <ol aria-label="Estornos do pagamento">{pagamento.estornos.map((estorno) => <li key={estorno.id}>
        <strong>Estorno · {moeda(estorno.valor)}</strong><span>Motivo: {estorno.motivo}</span>
        <span>Efetivado em {instanteRecife(estorno.efetivado_em)}</span><span>Registrado em {instanteRecife(estorno.registrado_em)}</span>
        <details><summary>Identificação do estorno</summary><span>{estorno.id}</span></details>
      </li>)}</ol>}
    </li>)}</ol>
  </section>;
}
