import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { Comanda } from '../../services/comandas';
import { instanteRecife, moeda } from '../../services/comandas';
import { useUsuario } from '../../services/usuario';
import { erroFinanceiro, podeConsultar, resultadoIncerto } from '../../services/financeiro';
import { aplicarBeneficio, chaveBeneficio, historicoBeneficios, lerBeneficio, limparBeneficio, podeBeneficiar, previaBeneficio, salvarBeneficio } from '../../services/beneficios';
import type { Beneficio, BeneficioPendente, PreviaBeneficio, ResultadoBeneficio, TipoDesconto } from '../../services/beneficios';

export function BeneficiosComanda({ comanda, bloqueado, aoBloqueio, aoAtualizar }: { comanda: Comanda; bloqueado: boolean; aoBloqueio: (b: boolean) => void; aoAtualizar: () => void }) {
  const usuario = useUsuario(), storage = chaveBeneficio(usuario.id, comanda);
  const [recuperacao] = useState(() => { try { return { pendente: lerBeneficio(storage), erro: '' }; } catch { return { pendente: null, erro: 'Benefício pendente inválido. Preserve os dados e procure o administrador.' }; } });
  const [pendente, setPendente] = useState(recuperacao.pendente);
  const [aberto, setAberto] = useState(false), [gratuidade, setGratuidade] = useState(false);
  const [alvo, setAlvo] = useState('comanda'), [tipo, setTipo] = useState<TipoDesconto>('nenhum'), [valor, setValor] = useState('0.00');
  const [motivo, setMotivo] = useState(''), [conferido, setConferido] = useState(false);
  const [revisao, setRevisao] = useState<{ previa: PreviaBeneficio; payload: Beneficio } | null>(null);
  const [ocupado, setOcupado] = useState(false), [erro, setErro] = useState(''), [aviso, setAviso] = useState('');
  const [historico, setHistorico] = useState<ResultadoBeneficio[]>([]), [erroHistorico, setErroHistorico] = useState(''), [consulta, setConsulta] = useState(0);
  const trava = useRef(false), montado = useRef(true);
  const permitido = podeBeneficiar(usuario, comanda), consultar = podeConsultar(usuario, comanda);
  const desabilitado = ocupado || bloqueado || !!recuperacao.erro;
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => { aoBloqueio(aberto || ocupado || !!pendente || !!recuperacao.erro); }, [aberto, ocupado, pendente, recuperacao.erro, aoBloqueio]);
  useEffect(() => {
    if (!consultar) return;
    const controller = new AbortController();
    historicoBeneficios(comanda, controller.signal).then(h => { if (!controller.signal.aborted) { setHistorico(h); setErroHistorico(''); } }).catch(() => { if (!controller.signal.aborted) setErroHistorico('Não foi possível carregar o histórico de benefícios.'); });
    return () => controller.abort();
  }, [comanda, consultar, consulta]);
  function selecionar(id: string) {
    setAlvo(id); const item = comanda.itens.find(i => i.id === id);
    setTipo(item?.desconto_tipo ?? (id === 'comanda' ? comanda.desconto_tipo ?? 'nenhum' : 'nenhum'));
    setValor(item?.desconto_valor ?? (id === 'comanda' ? comanda.desconto_valor ?? '0.00' : '0.00'));
  }
  function abrir(gratis: boolean) { selecionar('comanda'); setGratuidade(gratis); setAberto(true); setMotivo(''); setErro(''); setAviso(''); setRevisao(null); setConferido(false); }
  function cancelar() { setAberto(false); setRevisao(null); setConferido(false); setMotivo(''); }
  async function preparar(event: FormEvent) {
    event.preventDefault(); if (trava.current || desabilitado || !permitido) return;
    trava.current = true; setOcupado(true); setErro('');
    const payload: Beneficio = { acao: gratuidade ? 'encerramento_gratuito' : alvo === 'comanda' ? 'comanda' : 'item', versao: comanda.versao_itens ?? 0, motivo: motivo.trim(), ...(!gratuidade ? { desconto_tipo: tipo, desconto_valor: tipo === 'nenhum' || tipo === 'cortesia' ? '0.00' : valor.replace(',', '.'), ...(alvo !== 'comanda' ? { item_id: alvo } : {}) } : {}) };
    try { const previa = await previaBeneficio(comanda, payload); if (montado.current) { setRevisao({ previa, payload }); setConferido(false); } }
    catch (e) { if (montado.current) { setErro(erroFinanceiro(e)); aoAtualizar(); } }
    finally { trava.current = false; if (montado.current) setOcupado(false); }
  }
  async function enviar(p: BeneficioPendente) {
    if (trava.current || desabilitado) return;
    trava.current = true; setOcupado(true); setErro('');
    try { salvarBeneficio(storage, p); setPendente(p); }
    catch { setErro('Não foi possível preservar o benefício. Nenhuma alteração foi enviada.'); trava.current = false; setOcupado(false); return; }
    try {
      const result = await aplicarBeneficio(comanda, p);
      if (montado.current) {
        cancelar(); try { limparBeneficio(storage, p); setPendente(null); } catch { setErro('Benefício confirmado. Preserve a chave: não foi possível remover o registro temporário.'); }
        setAviso(result.fechado ? 'Benefício e encerramento confirmados, sem novo pagamento.' : 'Benefício confirmado. Total e saldo atualizados.'); setConsulta(n => n + 1);
      }
      aoAtualizar();
    } catch (e) {
      if (montado.current) {
        setErro(erroFinanceiro(e));
        if (!resultadoIncerto(e)) { try { limparBeneficio(storage, p); setPendente(null); setRevisao(null); } catch { /* preservar original */ } aoAtualizar(); }
      }
    } finally { trava.current = false; if (montado.current) setOcupado(false); }
  }
  const exige = revisao && (revisao.previa.exige_fechamento || revisao.previa.exige_gratuidade);
  return <section aria-label="Descontos e cortesias" className="comanda-adicionar-servico comanda-beneficios">
    <h4>Descontos e cortesias</h4>
    {erro && <p role="alert">{erro}</p>}{recuperacao.erro && <p role="alert">{recuperacao.erro}</p>}{aviso && <p role="status">{aviso}</p>}
    {pendente && <aside role="status"><p>Benefício aguardando confirmação. Recupere a operação original antes de iniciar outra.</p><button disabled={desabilitado} onClick={() => void enviar(pendente)}>Recuperar benefício original</button></aside>}
    {permitido && !aberto && !pendente && <><button disabled={desabilitado} onClick={() => abrir(false)}>Conceder ou alterar benefício</button>{comanda.itens.length > 0 && Number(comanda.total) === 0 && <button disabled={desabilitado} onClick={() => abrir(true)}>Encerrar comanda gratuita</button>}</>}
    {aberto && !revisao && !pendente && <form onSubmit={preparar}><fieldset disabled={desabilitado || !permitido}>
      <legend>{gratuidade ? 'Encerramento gratuito' : 'Benefício por serviço ou comanda'}</legend>
      {!gratuidade && <><label>Aplicar em<select value={alvo} onChange={e => selecionar(e.target.value)}><option value="comanda">Comanda inteira</option>{comanda.itens.filter(i => i.tipo === 'servico' && i.ativo !== false).map(i => <option key={i.id} value={i.id}>{i.descricao}</option>)}</select></label>
        <label>Tipo de benefício<select value={tipo} onChange={e => { setTipo(e.target.value as TipoDesconto); setValor('0.00'); }}><option value="nenhum">Sem desconto</option><option value="valor">Desconto em R$</option><option value="percentual">Desconto em %</option>{alvo !== 'comanda' && <option value="cortesia">Cortesia integral</option>}</select></label>
        {(tipo === 'valor' || tipo === 'percentual') && <label>{tipo === 'valor' ? 'Desconto em R$ sobre a linha ou comanda' : 'Percentual de desconto'}<input required type="number" min="0" max={tipo === 'percentual' ? '100' : '99999999.99'} step="0.01" value={valor} onChange={e => setValor(e.target.value)} /></label>}
        <p>Primeiro benefícios individuais e cortesias; depois o desconto geral sobre o subtotal restante. Valores em R$ são por linha, preservando o preço histórico.</p></>}
      {gratuidade && <p>Exige serviços ativos e total zero. O encerramento é explícito e não cria pagamento.</p>}
      <label>Motivo do benefício ou encerramento<textarea required maxLength={1000} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
      <button type="submit">Consultar prévia do benefício</button>
    </fieldset><button type="button" disabled={ocupado} onClick={cancelar}>Cancelar benefício</button></form>}
    {revisao && !pendente && <div role="group" aria-label="Revisão do benefício">
      <p>Total bruto: {moeda(revisao.previa.posterior.total_bruto)}. Benefícios individuais: {moeda(revisao.previa.posterior.desconto_itens)}. Subtotal: {moeda(revisao.previa.posterior.subtotal)}. Desconto geral: {moeda(revisao.previa.posterior.desconto_geral)}.</p>
      <p>Total: {moeda(revisao.previa.anterior.total)} → {moeda(revisao.previa.posterior.total)}. Recebido líquido: {moeda(revisao.previa.recebido_liquido)}. Novo saldo: {moeda(revisao.previa.saldo)}.</p>
      {exige ? <label><input type="checkbox" checked={conferido} onChange={e => setConferido(e.target.checked)} disabled={desabilitado} />{revisao.previa.exige_gratuidade ? 'Confirmo o encerramento gratuito dos serviços, sem pagamento fictício.' : 'Confirmo o benefício, a quitação pelo recebido e o fechamento financeiro, sem novo pagamento.'}</label> : <p>A comanda permanecerá aberta. Nenhum pagamento será criado.</p>}
      <button disabled={desabilitado || !permitido || (!!exige && !conferido)} onClick={() => void enviar({ chave: crypto.randomUUID(), payload: { ...revisao.payload, conferencia: revisao.previa.conferencia, confirmar_fechamento: revisao.previa.exige_fechamento && conferido, confirmar_gratuidade: revisao.previa.exige_gratuidade && conferido } })}>{exige ? 'Confirmar benefício e encerramento' : 'Confirmar benefício'}</button>
      <button disabled={ocupado} onClick={cancelar}>Cancelar benefício</button>
    </div>}
    {consultar && <details><summary>Histórico de benefícios e gratuidades</summary>{erroHistorico ? <><p role="alert">{erroHistorico}</p><button onClick={() => setConsulta(n => n + 1)}>Atualizar histórico de benefícios</button></> : <><p>{historico.length ? 'Valores históricos preservados:' : 'Nenhum benefício registrado.'}</p><ol>{historico.map(h => <li key={h.chave_idempotencia}>{instanteRecife(h.registrado_em)} · Responsável: {h.registrado_por} · {h.motivo}<p>{h.acao === 'encerramento_gratuito' ? 'Encerramento gratuito' : h.item_id ? 'Benefício individual' : 'Desconto geral'} · Total: {moeda(h.anterior.total)} → {moeda(h.posterior.total)}. Descontos individuais: {moeda(h.anterior.desconto_itens)} → {moeda(h.posterior.desconto_itens)}. Geral: {moeda(h.anterior.desconto_geral)} → {moeda(h.posterior.desconto_geral)}.{h.fechado ? ' Encerrada sem novo pagamento.' : ''}</p></li>)}</ol></>}</details>}
  </section>;
}
