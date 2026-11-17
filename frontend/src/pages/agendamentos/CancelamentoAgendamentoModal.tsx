import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import api from '../../services/api';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { consultarReagendamento, type ReservaReagendamento, type HistoricoReagendamento } from '../../services/reagendamento';
import { podeOperarAgenda, type UsuarioAgenda } from '../../services/permissoesAgenda';
import { mensagemErro, escritaIncerta } from '../../services/erros';

type Reserva = ReservaReagendamento & {
  cancelado_em?: string | null; cancelado_por?: string | null;
  cancelado_por_cliente?: string | null; motivo_cancelamento?: string | null;
};
interface Props {
  agendamentoId: string; historico: boolean; usuario: UsuarioAgenda;
  onFechar: () => void; onSalvo: () => void; onConferir: () => void;
}

export function CancelamentoAgendamentoModal({ agendamentoId, historico: somenteHistorico, usuario, onFechar, onSalvo, onConferir }: Props) {
  const [marca] = useState(contextoAtual);
  const [reserva, setReserva] = useState<Reserva | null>(null);
  const [historico, setHistorico] = useState<HistoricoReagendamento[]>([]);
  const [motivo, setMotivo] = useState('');
  const [confirmado, setConfirmado] = useState(false);
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [bloqueado, setBloqueado] = useState(false);
  const trava = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    consultarReagendamento(agendamentoId, marca, controller.signal).then(dados => {
      if (!controller.signal.aborted && contextoValido(marca)) {
        setReserva(dados.reserva); setHistorico(dados.historico);
      }
    }).catch(falha => {
      if (!controller.signal.aborted && contextoValido(marca)) setErro(mensagemErro(falha, 'Não foi possível consultar o agendamento.'));
    });
    return () => controller.abort();
  }, [agendamentoId, marca]);
  const permitido = reserva && !somenteHistorico && ['pendente', 'aguardando'].includes(reserva.status)
    && podeOperarAgenda(usuario, reserva.barbeiro_id) && !!reserva.atualizado_em;
  async function cancelar(event: React.FormEvent) {
    event.preventDefault();
    if (trava.current || bloqueado || !permitido || !confirmado || !motivo.trim()) return;
    if (!contextoValido(marca)) { setBloqueado(true); setErro('A sessão ou filial mudou. Reabra o agendamento.'); return; }
    trava.current = true; setOcupado(true); setErro('');
    try {
      const resposta = await api.patch<Reserva>(`/agendamentos/${encodeURIComponent(reserva.id)}/status`, {
        status: 'cancelado', atualizado_em_esperado: reserva.atualizado_em,
        motivo_cancelamento: motivo.trim(), confirmado: true,
      }, { params: { filial_id: marca.filialId } });
      if (!contextoValido(marca)) return;
      if (resposta.data.id !== reserva.id || resposta.data.filial_id !== marca.filialId || resposta.data.status !== 'cancelado') {
        throw new Error('Resposta incompatível. Feche e consulte o agendamento antes de repetir.');
      }
      onSalvo();
    } catch (falha) {
      if (!contextoValido(marca)) return;
      const incerto = escritaIncerta(falha) || !axios.isAxiosError(falha);
      const status = axios.isAxiosError(falha) ? falha.response?.status : undefined;
      setBloqueado(incerto || [403, 404, 409].includes(status ?? 0));
      setErro(mensagemErro(falha, 'Não foi possível cancelar o agendamento.') +
        (incerto ? ' Resultado não confirmado. Feche e consulte o histórico antes de reenviar.' : ''));
      if (incerto || status === 409) onConferir();
    } finally { trava.current = false; setOcupado(false); }
  }
  return <div className="modal-overlay"><section className="modal-box reagendamento-modal" role="dialog" aria-modal="true" aria-labelledby="cancelamento-agendamento-titulo">
    <h2 id="cancelamento-agendamento-titulo">{somenteHistorico ? 'Histórico do agendamento' : 'Cancelar agendamento'}</h2>
    {erro && <p role="alert">{erro}</p>}
    {!reserva && !erro && <p role="status">Consultando agendamento…</p>}
    {reserva && <>
      <p>{reserva.cliente.nome} · {reserva.data.split('-').reverse().join('/')} · {reserva.hora_inicio.slice(0, 5)} · {reserva.barbeiro.nome}</p>
      <p>Status: {reserva.status}</p>
      {reserva.status === 'cancelado' && <dl>
        <dt>Motivo do cancelamento</dt><dd>{reserva.motivo_cancelamento || 'Não informado no registro histórico'}</dd>
        <dt>Data e horário</dt><dd>{reserva.cancelado_em ? new Date(reserva.cancelado_em).toLocaleString('pt-BR') : 'Não informado'}</dd>
        <dt>Autor do cancelamento</dt><dd>{reserva.cancelado_por || reserva.cancelado_por_cliente || 'Não informado'}{reserva.cancelado_por_cliente ? ' (cliente)' : ''}</dd>
      </dl>}
      {!somenteHistorico && <form onSubmit={event => void cancelar(event)}><fieldset disabled={!permitido || ocupado || bloqueado}>
        <legend>Confirme o cancelamento desta reserva</legend>
        <p>O horário será liberado. Registros e histórico serão preservados. Pagamentos e fechamentos existentes podem impedir o cancelamento.</p>
        <label className="modal-campo">Motivo do cancelamento<textarea autoFocus required maxLength={1000} value={motivo} onChange={event => { setMotivo(event.target.value); setConfirmado(false); }} /></label>
        <label><input type="checkbox" checked={confirmado} onChange={event => setConfirmado(event.target.checked)} />Confirmo o cancelamento deste agendamento.</label>
        <button type="submit" className="modal-btn-salvar" disabled={!confirmado || !motivo.trim()}>{ocupado ? 'Cancelando…' : 'Confirmar cancelamento'}</button>
      </fieldset></form>}
      <details><summary>Histórico de reagendamentos ({historico.length})</summary>
        {!historico.length && <p>Nenhum reagendamento registrado.</p>}
        <ul>{historico.map(item => <li key={item.id}>{item.data_anterior} {item.hora_inicio_anterior} → {item.data_nova} {item.hora_inicio_nova}. {item.motivo || 'Sem motivo adicional'} · {item.registrado_em ? new Date(item.registrado_em).toLocaleString('pt-BR') : ''} · Autor: {item.registrado_por || item.registrado_por_cliente || 'Não informado'}</li>)}</ul>
      </details>
    </>}
    {bloqueado && <p role="status">Feche e consulte o agendamento atualizado antes de tentar novamente.</p>}
    <button type="button" className="modal-btn-cancelar" disabled={ocupado} onClick={onFechar}>Fechar e atualizar agenda</button>
  </section></div>;
}
