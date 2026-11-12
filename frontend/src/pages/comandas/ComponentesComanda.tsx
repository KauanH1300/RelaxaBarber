import { Icone } from '../../components/Icone';
import type { Comanda, IndicadoresComanda } from '../../services/comandas';
import { dataAtendimento, identificarComanda, moeda, statusAtendimento, statusComanda } from '../../services/comandas';

export function IconeComanda({ nome }: { nome: string }) {
  return <Icone nome={nome} />;
}
export function Indicadores({ dados, carregando }: { dados: IndicadoresComanda | null; carregando: boolean }) {
  const valor = (numero: number | undefined) => dados ? String(numero ?? 0) : '—';
  return <div className="comandas-indicadores" aria-label="Indicadores do período" aria-busy={carregando}>
    <article className="comanda-indicador"><div><h2>Comandas abertas</h2><IconeComanda nome="receipt_long" /></div>
      <strong>{valor(dados?.contagens.aberta)}</strong><p>Chegada registrada ou atendimento iniciado</p></article>
    <article className="comanda-indicador"><div><h2>Valor em aberto</h2><IconeComanda nome="payments" /></div>
      <strong>{dados ? moeda(dados.valor_abertas) : '—'}</strong><p>Soma dos itens das comandas abertas</p></article>
    <article className="comanda-indicador comanda-indicador-indisponivel"><div><h2>Aguardando pagamento</h2><IconeComanda nome="credit_card_off" /></div>
      <strong>Indisponível</strong><p>Pagamentos ainda não são registrados</p></article>
    <article className="comanda-indicador"><div><h2>Fechadas no período</h2><IconeComanda nome="task_alt" /></div>
      <strong>{valor(dados?.contagens.fechada)}</strong><p>Pela data do atendimento · não indica quitação</p></article>
  </div>;
}
export function ItensComanda({ comanda }: { comanda: Comanda }) {
  return comanda.itens.length ? <ul className="comanda-itens">{comanda.itens.map((item) => <li key={item.id}>
    <div><span className="comanda-quantidade">{item.quantidade}×</span><span>{item.descricao}</span></div>
    <div className="comanda-item-preco"><small>{moeda(item.preco_unitario)} / un.</small><strong>{moeda(item.subtotal)}</strong></div>
  </li>)}</ul> : <p className="comanda-sem-itens">Nenhum item registrado.</p>;
}
export function CardComanda({ comanda, aoDetalhar }: { comanda: Comanda; aoDetalhar: (id: string) => void }) {
  return <article className={`comanda-card comanda-card-${comanda.status}`}>
    <header><div className="comanda-card-identificacao"><span title={comanda.id}>{identificarComanda(comanda.id)}</span>
      <span className={`comanda-status comanda-status-${comanda.status}`}>{statusComanda[comanda.status] ?? comanda.status}</span></div>
      <div className="comanda-pessoa"><span className="comanda-avatar" aria-hidden="true">{comanda.cliente.nome.trim().split(/\s+/).slice(0, 2).map((n) => n[0]).join('')}</span>
        <div><h2>{comanda.cliente.nome}</h2><p><IconeComanda nome="person" />{comanda.profissional.nome}</p></div></div>
      <p className="comanda-agendamento"><IconeComanda nome="schedule" />{dataAtendimento(comanda.atendimento.data)} · {comanda.atendimento.hora_inicio.slice(0, 5)}–{comanda.atendimento.hora_fim.slice(0, 5)}</p>
      <p className="comanda-atendimento-status">Atendimento: {statusAtendimento[comanda.atendimento.status] ?? comanda.atendimento.status}</p>
    </header>
    <div className="comanda-card-corpo"><h3>Itens da comanda <span>({comanda.itens.length})</span></h3><ItensComanda comanda={comanda} /></div>
    <footer><div><span>Total dos itens</span><strong>{moeda(comanda.total)}</strong></div>
      <button type="button" onClick={() => aoDetalhar(comanda.id)} aria-label={`Ver comanda de ${comanda.cliente.nome}, ${comanda.id}`}>
        Ver comanda <IconeComanda nome="arrow_forward" /></button></footer>
  </article>;
}
