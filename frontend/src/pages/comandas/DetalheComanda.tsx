import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { Comanda } from '../../services/comandas';
import { classificacaoComanda, dataAtendimento, detalharComanda, erroConsultaComanda, identificarComanda, instanteRecife, moeda, statusAtendimento, statusApresentacao, statusComanda } from '../../services/comandas';
import { FinanceiroComanda } from './FinanceiroComanda';
import { IconeComanda, ItensComanda } from './ComponentesComanda';
import { AdicionarServico } from './AdicionarServico';

export function ConteudoDetalhe({ comanda, acoes }: { comanda: Comanda; acoes?: ReactNode }) {
  const estado = classificacaoComanda(comanda);
  return <>
    <div className="comanda-detalhe-pessoas">
      <section className="comanda-detalhe-pessoa" aria-label="Cliente da comanda">
        <span className="comanda-avatar" aria-hidden="true">{comanda.cliente.nome.trim().split(/\s+/).slice(0, 2).map((nome) => nome[0]).join('')}</span>
        <div><p>Cliente</p><h3>{comanda.cliente.nome}</h3></div>
        <span className={`comanda-status comanda-status-${estado}`}>{statusApresentacao[estado]}</span>
      </section>
      <section className="comanda-detalhe-profissional" aria-label="Profissional responsável">
        <span className="comanda-avatar" aria-hidden="true"><IconeComanda nome="person" /></span>
        <div><p>Profissional responsável</p><h3>{comanda.profissional.nome}</h3><span>{comanda.filial.nome}</span></div>
      </section>
    </div>
    <section className="comanda-detalhe-informacoes" aria-labelledby="comanda-informacoes-titulo">
    <h3 id="comanda-informacoes-titulo" className="comanda-detalhe-subtitulo">Informações da comanda</h3>
    <dl className="comanda-detalhe-dados">
      <div><dt>Profissional</dt><dd>{comanda.profissional.nome}</dd></div>
      <div><dt>Filial</dt><dd>{comanda.filial.nome}</dd></div>
      <div><dt>Data do atendimento</dt><dd>{dataAtendimento(comanda.atendimento.data)}</dd></div>
      <div><dt>Horário · America/Recife</dt><dd>{comanda.atendimento.hora_inicio.slice(0, 5)}–{comanda.atendimento.hora_fim.slice(0, 5)}</dd></div>
      <div><dt>Atendimento</dt><dd>{statusAtendimento[comanda.atendimento.status] ?? comanda.atendimento.status}</dd></div>
      <div><dt>Abertura da comanda</dt><dd>{instanteRecife(comanda.data_abertura)}</dd></div>
      <div><dt>Estado operacional histórico</dt><dd>{statusComanda[comanda.status]} · não comprova quitação</dd></div>
      <div><dt>Fechamento operacional histórico</dt><dd>{instanteRecife(comanda.data_fechamento)}</dd></div>
      <div><dt>Fechamento financeiro comprovado</dt><dd>{instanteRecife(comanda.fechamento_financeiro_em ?? null)}</dd></div>
    </dl>
    </section>
    <section className="comanda-detalhe-servicos" aria-labelledby="comanda-servicos-titulo">
    <h3 id="comanda-servicos-titulo" className="comanda-detalhe-subtitulo">Serviços e itens <span>({comanda.itens.length})</span></h3><ItensComanda comanda={comanda} tabela />
    {acoes}
    <div className="comanda-detalhe-total"><span>Total dos itens</span><strong>{moeda(comanda.total)}</strong></div>
    </section>
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
  const [financeiroBloqueado, setFinanceiroBloqueado] = useState(true);
  const [motivoFinanceiro, setMotivoFinanceiro] = useState('Aguarde a consulta financeira antes de adicionar serviços.');
  const atualizarBloqueioFinanceiro = useCallback((bloqueado: boolean, motivo?: string) => {
    setFinanceiroBloqueado(bloqueado); setMotivoFinanceiro(motivo ?? '');
  }, []);
  const [itensBloqueados, setItensBloqueados] = useState(true);
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
      const detalhesFechados = [...event.currentTarget.querySelectorAll('details:not([open])')];
      const controles = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, a[href], [tabindex="0"]')]
        .filter((elemento) => elemento.getClientRects().length > 0 && detalhesFechados.every((detalhe) => !detalhe.contains(elemento) || detalhe.querySelector(':scope > summary') === elemento));
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
        {comanda && <div className="comanda-detalhe-layout"><div className="comanda-detalhe-operacional"><ConteudoDetalhe comanda={comanda} acoes={<AdicionarServico comanda={comanda} bloqueado={financeiroBloqueado || !!erro} motivoBloqueio={erro ? 'Não foi possível atualizar os detalhes da comanda. Tente novamente antes de adicionar serviços.' : motivoFinanceiro} aoBloqueio={setItensBloqueados} aoAtualizar={() => { if (dialogo.current?.open) setTentativa((n) => n + 1); aoAtualizar?.(); }} />} /></div><FinanceiroComanda comanda={comanda} bloqueioExterno={itensBloqueados} aoBloqueio={atualizarBloqueioFinanceiro} aoConfirmar={() => { if (dialogo.current?.open) setTentativa((n) => n + 1); aoAtualizar?.(); }} /></div>}
      </>}
    </div>
  </dialog>;
}
