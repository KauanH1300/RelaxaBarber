import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { Comanda } from '../../services/comandas';
import { instanteRecife, moeda } from '../../services/comandas';
import { useUsuario } from '../../services/usuario';
import { catalogoItens } from '../../services/itensComanda';
import type { ServicoParaComanda } from '../../services/itensComanda';
import { erroFinanceiro, podeConsultar, resultadoIncerto } from '../../services/financeiro';
import { aplicarAjuste, chaveAjuste, historicoAjustes, lerAjuste, limparAjuste, podeAjustar, previaAjuste, salvarAjuste } from '../../services/alteracoesItens';
import type { Ajuste, AjustePendente, PreviaAjuste, ResultadoAjuste } from '../../services/alteracoesItens';

export function EditarServicos({ comanda, bloqueado, aoBloqueio, aoAtualizar }: { comanda: Comanda; bloqueado: boolean; aoBloqueio: (b: boolean) => void; aoAtualizar: () => void }) {
  const usuario = useUsuario();
  const storage = chaveAjuste(usuario.id, comanda);
  const [recuperacao] = useState(() => { try { return { pendente: lerAjuste(storage), erro: '' }; } catch { return { pendente: null, erro: 'Não foi possível ler o ajuste pendente. Preserve os dados e procure o administrador.' }; } });
  const [pendente, setPendente] = useState(recuperacao.pendente);
  const [itemId, setItemId] = useState('');
  const [acao, setAcao] = useState<Ajuste['acao']>('quantidade');
  const [quantidade, setQuantidade] = useState('1');
  const [servico, setServico] = useState('');
  const [motivo, setMotivo] = useState('');
  const [catalogo, setCatalogo] = useState<ServicoParaComanda[]>([]);
  const [previsualizacao, setPrevisualizacao] = useState<{ previa: PreviaAjuste; payload: Ajuste } | null>(null);
  const [conferido, setConferido] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const [historico, setHistorico] = useState<ResultadoAjuste[]>([]);
  const [erroHistorico, setErroHistorico] = useState('');
  const [revisao, setRevisao] = useState(0);
  const trava = useRef(false);
  const consultaPermitida = podeConsultar(usuario, comanda);
  const montado = useRef(true);
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => { aoBloqueio(!!itemId || ocupado || !!pendente || !!recuperacao.erro); }, [itemId, ocupado, pendente, recuperacao.erro, aoBloqueio]);
  useEffect(() => {
    if (!consultaPermitida) return;
    const controller = new AbortController();
    historicoAjustes(comanda, controller.signal).then(r => { if (!controller.signal.aborted) { setHistorico(r); setErroHistorico(''); } }).catch(() => { if (!controller.signal.aborted) setErroHistorico('Não foi possível carregar o histórico de ajustes.'); });
    return () => controller.abort();
  }, [comanda, revisao, consultaPermitida]);
  useEffect(() => {
    if (acao !== 'substituir' || !itemId) return;
    const controller = new AbortController();
    catalogoItens(controller.signal).then(r => { if (!controller.signal.aborted) setCatalogo(r); }).catch(() => { if (!controller.signal.aborted) setErro('Não foi possível carregar o catálogo. Cancele e tente novamente.'); });
    return () => controller.abort();
  }, [acao, itemId]);
  const permitido = podeAjustar(usuario, comanda);
  const alvo = comanda.itens.find(i => i.id === itemId);
  const desabilitado = bloqueado || ocupado || !!recuperacao.erro;
  function abrir(id: string, operacao: Ajuste['acao']) {
    setItemId(id); setAcao(operacao); setQuantidade(String(comanda.itens.find(i => i.id === id)?.quantidade ?? 1));
    setServico(''); setMotivo(''); setPrevisualizacao(null); setConferido(false); setErro(''); setAviso('');
  }
  function cancelar() { setItemId(''); setPrevisualizacao(null); setConferido(false); setErro(''); }
  async function preparar(event: FormEvent) {
    event.preventDefault(); if (trava.current || desabilitado || !permitido || !alvo) return;
    trava.current = true; setOcupado(true); setErro('');
    const payload: Ajuste = { acao, versao: comanda.versao_itens ?? 0, motivo: motivo.trim(), ...(acao !== 'remover' ? { quantidade: Number(quantidade) } : {}), ...(acao === 'substituir' ? { servico_id: servico } : {}) };
    try {
      const previa = await previaAjuste(comanda, itemId, payload);
      if (montado.current) { setPrevisualizacao({ previa, payload }); setConferido(false); }
    } catch (e) { if (montado.current) { setErro(erroFinanceiro(e)); aoAtualizar(); } }
    finally { trava.current = false; if (montado.current) setOcupado(false); }
  }
  async function enviar(p: AjustePendente) {
    if (trava.current || desabilitado) return;
    trava.current = true; setOcupado(true); setErro('');
    try { salvarAjuste(storage, p); setPendente(p); }
    catch { setErro('Não foi possível preservar o ajuste. Nenhuma alteração foi enviada.'); trava.current = false; setOcupado(false); return; }
    try {
      const resultado = await aplicarAjuste(comanda, p);
      if (montado.current) {
        cancelar();
        try { limparAjuste(storage, p); setPendente(null); }
        catch { setErro('Ajuste confirmado. Preserve a chave: o registro temporário não pôde ser removido.'); }
        setAviso(resultado.fechado ? 'Ajuste e fechamento confirmados, sem novo pagamento.' : 'Ajuste confirmado. Total e saldo atualizados.'); setRevisao(n => n + 1);
      }
      aoAtualizar();
    } catch (e) {
      if (montado.current) {
        setErro(erroFinanceiro(e));
        if (!resultadoIncerto(e)) {
          try { limparAjuste(storage, p); setPendente(null); setPrevisualizacao(null); } catch { /* preservar original */ }
          aoAtualizar();
        }
      }
    } finally { trava.current = false; if (montado.current) setOcupado(false); }
  }
  return <section aria-label="Ajustes dos serviços" className="comanda-adicionar-servico comanda-editar-servicos">
    {erro && <p role="alert">{erro}</p>}{aviso && <p role="status">{aviso}</p>}{recuperacao.erro && <p role="alert">{recuperacao.erro}</p>}
    {pendente && <aside role="status"><p>Ajuste aguardando confirmação. Recupere a operação original, sem criar outro ajuste.</p><button type="button" disabled={desabilitado} onClick={() => void enviar(pendente)}>Recuperar ajuste original</button></aside>}
    {permitido && !itemId && !pendente && <ul>{comanda.itens.filter(i => i.tipo === 'servico' && i.ativo !== false).map(i => <li key={i.id}>
      <span>{i.descricao}</span>{(['quantidade', 'substituir', 'remover'] as const).map(a => <button key={a} type="button" disabled={desabilitado} onClick={() => abrir(i.id, a)} aria-label={`${a === 'quantidade' ? 'Editar quantidade de' : a === 'substituir' ? 'Substituir' : 'Remover'} ${i.descricao}`}>{a === 'quantidade' ? 'Editar quantidade' : a === 'substituir' ? 'Substituir serviço' : 'Remover serviço'}</button>)}
    </li>)}</ul>}
    {itemId && !pendente && !previsualizacao && <form onSubmit={preparar}><fieldset disabled={desabilitado || !permitido}>
      <legend>{acao === 'remover' ? 'Remover serviço' : acao === 'substituir' ? 'Substituir serviço' : 'Editar quantidade'}: {alvo?.descricao}</legend>
      {acao !== 'remover' && <label>Nova quantidade<input required type="number" min="1" max="999" step="1" value={quantidade} onChange={e => setQuantidade(e.target.value)} /></label>}
      {acao === 'substituir' && <label>Novo serviço<select required value={servico} onChange={e => setServico(e.target.value)}><option value="">Selecione</option>{catalogo.map(s => <option key={s.id} value={s.id}>{s.nome} · {moeda(String(s.preco))}</option>)}</select></label>}
      <p>{acao === 'quantidade' ? 'O preço unitário histórico será preservado e os benefícios serão recalculados.' : acao === 'substituir' ? 'O preço do novo serviço será validado pelo catálogo. Ao trocar de serviço, o benefício individual anterior será removido.' : 'O serviço será removido do total, preservando seu histórico. O desconto geral será recalculado.'}</p>
      <label>Motivo do ajuste<textarea required maxLength={1000} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
      <button type="submit">Consultar prévia do ajuste</button>
    </fieldset><button type="button" disabled={ocupado} onClick={cancelar}>Cancelar ajuste</button></form>}
    {previsualizacao && !pendente && <div role="group" aria-label="Revisão do ajuste">
      <p>{previsualizacao.previa.anterior.descricao} → {previsualizacao.previa.posterior.ativo === false ? 'Removido' : previsualizacao.previa.posterior.descricao}</p>
      <p>Total: {moeda(previsualizacao.previa.total_anterior)} → {moeda(previsualizacao.previa.total)}. Recebido líquido: {moeda(previsualizacao.previa.recebido_liquido)}. Novo saldo: {moeda(previsualizacao.previa.saldo)}.</p>
      {previsualizacao.previa.exige_fechamento ? <label><input type="checkbox" checked={conferido} onChange={e => setConferido(e.target.checked)} disabled={desabilitado} />Confirmo o ajuste, a quitação pelo valor já recebido e o fechamento financeiro, sem novo pagamento.</label> : <p>A comanda permanecerá aberta. Nenhum pagamento será criado.</p>}
      <button type="button" disabled={desabilitado || !permitido || (previsualizacao.previa.exige_fechamento && !conferido)} onClick={() => void enviar({ itemId, chave: crypto.randomUUID(), payload: { ...previsualizacao.payload, conferencia: previsualizacao.previa.conferencia, confirmar_fechamento: previsualizacao.previa.exige_fechamento && conferido } })}>{previsualizacao.previa.exige_fechamento ? 'Confirmar ajuste e fechamento' : 'Confirmar ajuste'}</button>
      <button type="button" disabled={ocupado} onClick={cancelar}>Cancelar ajuste</button>
    </div>}
    {consultaPermitida && <details><summary>Histórico de ajustes dos serviços</summary>{erroHistorico && <><p role="alert">{erroHistorico}</p><button onClick={() => setRevisao(n => n + 1)}>Atualizar histórico de ajustes</button></>}
      {!erroHistorico && !historico.length && <p>Nenhum ajuste registrado.</p>}
      <ol>{historico.map(h => <li key={h.chave_idempotencia}>{instanteRecife(h.registrado_em)} · Responsável: {h.registrado_por} · {h.motivo}<p>{h.anterior.descricao}: {h.anterior.quantidade} × {moeda(h.anterior.preco_unitario)} → {h.posterior.ativo === false ? 'Removido' : `${h.posterior.descricao}: ${h.posterior.quantidade} × ${moeda(h.posterior.preco_unitario)}`}. Total: {moeda(h.total_anterior)} → {moeda(h.total)}.{h.fechado ? ' Fechamento financeiro confirmado, sem novo pagamento.' : ''}</p></li>)}</ol>
    </details>}
  </section>;
}
