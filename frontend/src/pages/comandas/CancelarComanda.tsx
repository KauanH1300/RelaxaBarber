import { useEffect, useRef, useState } from 'react';
import type { Comanda } from '../../services/comandas';
import { instanteRecife } from '../../services/comandas';
import { useUsuario } from '../../services/usuario';
import { erroFinanceiro, resultadoIncerto } from '../../services/financeiro';
import { cancelarComanda, chaveCancelamento, lerCancelamento, salvarCancelamento, podeCancelarComanda } from '../../services/cancelamentoComanda';
import type { CancelamentoPendente } from '../../services/cancelamentoComanda';

export function CancelarComanda({ comanda, bloqueado, aoBloqueio, aoAtualizar }: {
  comanda: Comanda; bloqueado: boolean; aoBloqueio: (b: boolean) => void; aoAtualizar: () => void;
}) {
  const usuario = useUsuario(), chave = chaveCancelamento(usuario.id, comanda);
  const [recuperacao] = useState(() => { try { return { pendente: lerCancelamento(chave), erro: '' }; } catch { return { pendente: null, erro: 'Não foi possível recuperar o cancelamento. Preserve os dados e procure o administrador.' }; } });
  const [pendente, setPendente] = useState(recuperacao.pendente);
  const [aberto, setAberto] = useState(false), [motivo, setMotivo] = useState('');
  const [confirmado, setConfirmado] = useState(false), [ocupado, setOcupado] = useState(false), [erro, setErro] = useState('');
  const trava = useRef(false), montado = useRef(true);
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => { aoBloqueio(aberto || ocupado || !!pendente || !!recuperacao.erro); }, [aberto, ocupado, pendente, recuperacao.erro, aoBloqueio]);
  async function enviar(p: CancelamentoPendente) {
    if (trava.current || bloqueado || recuperacao.erro) return;
    trava.current = true; setOcupado(true); setErro('');
    try { salvarCancelamento(chave, p); setPendente(p); }
    catch { setErro('Não foi possível preservar o cancelamento. Nenhuma alteração foi enviada.'); trava.current = false; setOcupado(false); return; }
    try {
      await cancelarComanda(comanda, p);
      localStorage.removeItem(chave);
      if (montado.current) { setPendente(null); setAberto(false); setConfirmado(false); }
      aoAtualizar();
    } catch (e) {
      if (montado.current) {
        setErro(erroFinanceiro(e));
        if (!resultadoIncerto(e)) {
          try { localStorage.removeItem(chave); setPendente(null); setAberto(false); } catch { /* preservar intenção */ }
          aoAtualizar();
        }
      }
    } finally { trava.current = false; if (montado.current) setOcupado(false); }
  }
  const permitido = podeCancelarComanda(usuario, comanda);
  return <section className="comanda-adicionar-servico comanda-cancelamento" aria-label="Cancelamento da comanda">
    {comanda.cancelamento && <p role="status">Comanda cancelada em {instanteRecife(comanda.cancelamento.registrado_em)} por {comanda.cancelamento.registrado_por}. Motivo: {comanda.cancelamento.motivo}.{comanda.tipo === 'avulsa' ? ' Os produtos foram repostos no estoque.' : ' O agendamento foi preservado.'}</p>}
    {(erro || recuperacao.erro) && <p role="alert">{erro || recuperacao.erro}</p>}
    {pendente ? <><p role="status">Cancelamento aguardando confirmação. Recupere a operação original antes de tentar novamente.</p><button disabled={ocupado || bloqueado || !!recuperacao.erro} onClick={() => void enviar(pendente)}>Recuperar cancelamento original</button></> : permitido && !recuperacao.erro && <>
      {!aberto ? <button disabled={bloqueado} onClick={() => { setAberto(true); setErro(''); }}>{comanda.tipo === 'avulsa' ? 'Cancelar venda avulsa' : 'Cancelar comanda vazia'}</button> : <form onSubmit={event => { event.preventDefault(); if (confirmado && motivo.trim()) void enviar({ chave: crypto.randomUUID(), payload: { versao: comanda.versao_itens ?? 0, motivo: motivo.trim(), confirmado: true } }); }}>
        <p>{comanda.tipo === 'avulsa' ? 'Produtos ativos serão repostos ao estoque. O cancelamento exige ausência de histórico financeiro.' : 'Cancelar apenas esta comanda, preservando seus registros e o agendamento vinculado. O cancelamento exige ausência de itens ativos e movimentações financeiras.'}</p>
        <label>Motivo do cancelamento<textarea required maxLength={1000} value={motivo} disabled={ocupado} onChange={e => setMotivo(e.target.value)} /></label>
        <label><input type="checkbox" checked={confirmado} disabled={ocupado} onChange={e => setConfirmado(e.target.checked)} />{comanda.tipo === 'avulsa' ? 'Confirmo o cancelamento e a reposição dos produtos.' : 'Confirmo o cancelamento da comanda, sem cancelar o agendamento.'}</label>
        <button type="submit" disabled={ocupado || bloqueado || !confirmado || !motivo.trim()}>Confirmar cancelamento da comanda</button>
        <button type="button" disabled={ocupado} onClick={() => { setAberto(false); setConfirmado(false); setMotivo(''); }}>Voltar sem cancelar</button>
      </form>}
    </>}
  </section>;
}
