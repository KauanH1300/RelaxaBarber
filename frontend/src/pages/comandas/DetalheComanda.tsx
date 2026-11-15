import { useEffect, useRef, useState } from 'react';
import type { Comanda } from '../../services/comandas';
import { dataAtendimento, detalharComanda, erroConsultaComanda, identificarComanda, instanteRecife, moeda, statusAtendimento, statusComanda } from '../../services/comandas';
import { FinanceiroComanda } from './FinanceiroComanda';
import { IconeComanda, ItensComanda } from './ComponentesComanda';

export function ConteudoDetalhe({ comanda }: { comanda: Comanda }) {
  return <>
    <div className="comanda-detalhe-pessoa"><h3>{comanda.cliente.nome}</h3><span className={`comanda-status comanda-status-${comanda.status}`}>{statusComanda[comanda.status] ?? comanda.status}</span></div>
    <dl className="comanda-detalhe-dados">
      <div><dt>Profissional</dt><dd>{comanda.profissional.nome}</dd></div>
      <div><dt>Filial</dt><dd>{comanda.filial.nome}</dd></div>
      <div><dt>Data do atendimento</dt><dd>{dataAtendimento(comanda.atendimento.data)}</dd></div>
      <div><dt>Horário · America/Recife</dt><dd>{comanda.atendimento.hora_inicio.slice(0, 5)}–{comanda.atendimento.hora_fim.slice(0, 5)}</dd></div>
      <div><dt>Atendimento</dt><dd>{statusAtendimento[comanda.atendimento.status] ?? comanda.atendimento.status}</dd></div>
      <div><dt>Abertura da comanda</dt><dd>{instanteRecife(comanda.data_abertura)}</dd></div>
      <div><dt>Fechamento registrado da comanda</dt><dd>{instanteRecife(comanda.data_fechamento)}</dd></div>
    </dl>
    <h3 className="comanda-detalhe-subtitulo">Serviços e itens</h3><ItensComanda comanda={comanda} />
    <div className="comanda-detalhe-total"><span>Total dos itens</span><strong>{moeda(comanda.total)}</strong></div>
    <p className="comanda-aviso"><IconeComanda nome="info" />Atendimento concluído e comanda fechada são estados distintos. Em registros históricos, o status isolado não comprova pagamento recebido. Consulte o financeiro verificado.</p>
    <details className="comanda-identificadores"><summary>Identificadores completos</summary>
      <dl><dt>Comanda</dt><dd>{comanda.id}</dd><dt>Agendamento</dt><dd>{comanda.agendamento_id}</dd></dl>
    </details>
  </>;
}

export function DetalheComanda({ id, aoFechar, aoAtualizar }: { id: string; aoFechar: () => void; aoAtualizar?: () => void }) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [comanda, setComanda] = useState<Comanda | null>(null);
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    const alvo = dialogo.current;
    const anterior = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    alvo?.showModal();
    return () => { alvo?.close(); if (anterior?.isConnected) anterior.focus(); else document.querySelector<HTMLButtonElement>('.comandas-cabecalho button')?.focus(); };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    detalharComanda(id, controller.signal).then((dados) => {
      if (!controller.signal.aborted) { setComanda(dados); setErro(''); }
    }).catch((falha: unknown) => {
      if (!controller.signal.aborted) {
        setErro(erroConsultaComanda(falha, true));
        const status = (falha as { response?: { status?: number } })?.response?.status;
        if (status && [401, 403, 404].includes(status)) setComanda(null);
      }
    }).finally(() => { if (!controller.signal.aborted) setCarregando(false); });
    return () => controller.abort();
  }, [id, tentativa]);
  return <dialog ref={dialogo} className="comanda-dialogo" aria-labelledby="comanda-detalhe-titulo" onCancel={(event) => { event.preventDefault(); aoFechar(); }}
    onKeyDown={(event) => {
      if (event.key !== 'Tab') return;
      const controles = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, a[href], [tabindex="0"]')]
        .filter((elemento) => elemento.getClientRects().length > 0);
      const primeiro = controles[0];
      const ultimo = controles.at(-1);
      if (event.shiftKey && document.activeElement === primeiro) { event.preventDefault(); ultimo?.focus(); }
      else if (!event.shiftKey && document.activeElement === ultimo) { event.preventDefault(); primeiro?.focus(); }
    }}>
    <header><div><p>Detalhes da comanda</p><h2 id="comanda-detalhe-titulo">{identificarComanda(id)}</h2></div>
      <button type="button" autoFocus onClick={aoFechar} aria-label="Fechar detalhes"><IconeComanda nome="close" /></button></header>
    <div className="comanda-dialogo-conteudo" aria-busy={carregando}>
      {carregando ? <p role="status">Carregando detalhes da comanda…</p> : <>
        {erro && <div className="comandas-estado"><p role="alert">{erro}</p><button onClick={() => { if (!comanda) setCarregando(true); setTentativa((n) => n + 1); }}>Tentar novamente</button></div>}
        {comanda && <><ConteudoDetalhe comanda={comanda} /><FinanceiroComanda comanda={comanda} aoConfirmar={() => { if (dialogo.current?.open) setTentativa((n) => n + 1); aoAtualizar?.(); }} /></>}
      </>}
    </div>
  </dialog>;
}
