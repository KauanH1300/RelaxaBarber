import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { consultarReagendamento, salvarReagendamento, podeReagendar } from '../../services/reagendamento';
import type { ReservaReagendamento, HistoricoReagendamento } from '../../services/reagendamento';
import type { ProfissionalAgenda, UsuarioAgenda } from '../../services/permissoesAgenda';
import { mensagemErro, escritaIncerta } from '../../services/erros';

interface Props {
  agendamentoId: string; usuario: UsuarioAgenda; barbeiros: ProfissionalAgenda[];
  onFechar: () => void; onSalvo: (data: string) => void; onConferir: () => void;
}

export function ReagendamentoModal({ agendamentoId, usuario, barbeiros, onFechar, onSalvo, onConferir }: Props) {
  const [marca] = useState(contextoAtual);
  const [reserva, setReserva] = useState<ReservaReagendamento | null>(null);
  const [historico, setHistorico] = useState<HistoricoReagendamento[]>([]);
  const [data, setData] = useState(''); const [hora, setHora] = useState('');
  const [barbeiroId, setBarbeiroId] = useState(''); const [motivo, setMotivo] = useState('');
  const [erro, setErro] = useState(''); const [salvando, setSalvando] = useState(false);
  const [bloqueado, setBloqueado] = useState(false); const enviando = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    consultarReagendamento(agendamentoId, marca, controller.signal).then(({ reserva: r, historico: h }) => {
      if (!controller.signal.aborted && contextoValido(marca)) {
        setReserva(r); setHistorico(h); setData(r.data); setHora(r.hora_inicio); setBarbeiroId(r.barbeiro_id);
      }
    }).catch(e => { if (!controller.signal.aborted && contextoValido(marca)) setErro(mensagemErro(e, 'Não foi possível consultar o atendimento. Feche e tente novamente.')); });
    return () => controller.abort();
  }, [agendamentoId, marca]);
  async function salvar(e: React.FormEvent) {
    e.preventDefault(); if (enviando.current || bloqueado || !reserva) return;
    enviando.current = true; setSalvando(true); setErro('');
    try {
      const resultado = await salvarReagendamento(reserva, { data, hora_inicio: hora, barbeiro_id: barbeiroId, motivo }, usuario, marca);
      if (contextoValido(marca)) onSalvo(resultado.data);
    } catch (falha) {
      if (!contextoValido(marca)) return;
      const incerto = escritaIncerta(falha);
      const status = axios.isAxiosError(falha) ? falha.response?.status : undefined;
      setBloqueado(incerto || [403, 404, 409].includes(status ?? 0));
      setErro((!axios.isAxiosError(falha) && falha instanceof Error ? falha.message : mensagemErro(falha, 'Não foi possível reagendar. Revise data, horário e barbeiro.')) +
        (incerto ? ' Resultado não confirmado. Feche e consulte o atendimento antes de reenviar.' : ''));
      if (incerto || status === 409) onConferir();
    } finally { enviando.current = false; setSalvando(false); }
  }
  const permitido = reserva && podeReagendar(usuario, reserva.barbeiro_id, reserva.status);
  const profissional = (id: string) => barbeiros.find(b => b.id === id)?.nome ?? id;
  const dia = (d: string) => d.split('-').reverse().join('/');
  return <div className="modal-overlay"><section className="modal-box reagendamento-modal" role="dialog" aria-modal="true" aria-labelledby="reagendamento-titulo">
    <h2 id="reagendamento-titulo">Reagendar atendimento</h2>
    {erro && <p role="alert" className="modal-erro">{erro}</p>}
    {!reserva && !erro && <p role="status">Carregando atendimento…</p>}
    {reserva && <>
      <p>{reserva.cliente.nome} — {dia(reserva.data)} às {reserva.hora_inicio.slice(0, 5)}, {reserva.barbeiro.nome}</p>
      {!permitido && <p role="alert">Este atendimento não pode ser reagendado pelo seu perfil ou estado atual.</p>}
      <form onSubmit={e => void salvar(e)}><fieldset disabled={salvando || bloqueado || !permitido}>
        <legend>Novo horário e profissional</legend>
        <label className="modal-campo">Data<input required type="date" value={data} onChange={e => setData(e.target.value)} /></label>
        <label className="modal-campo">Horário<input required type="time" step="1" value={hora} onChange={e => setHora(e.target.value)} /></label>
        <label className="modal-campo">Barbeiro<select required value={barbeiroId} onChange={e => setBarbeiroId(e.target.value)}><option value="">Selecione…</option>{barbeiros.map(b => <option key={b.id} value={b.id}>{b.nome}</option>)}</select></label>
        <label className="modal-campo">Motivo (opcional)<input maxLength={1000} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
        <p>A duração e os serviços são preservados. O novo horário deve respeitar o expediente, a jornada e as reservas existentes.</p>
        <button className="modal-btn-salvar" type="submit">{salvando ? 'Reagendando…' : 'Confirmar reagendamento'}</button>
      </fieldset></form>
      <details><summary>Histórico de reagendamentos ({historico.length})</summary>
        {!historico.length && <p>Nenhum reagendamento registrado.</p>}
        <ul>{historico.map(h => <li key={h.id}>{dia(h.data_anterior)} {h.hora_inicio_anterior.slice(0, 5)} ({profissional(h.barbeiro_id_anterior)}) → {dia(h.data_nova)} {h.hora_inicio_nova.slice(0, 5)} ({profissional(h.barbeiro_id_novo)}). {h.motivo}</li>)}</ul>
      </details>
    </>}
    {bloqueado && <p role="status">Feche o formulário e consulte o atendimento atualizado antes de tentar novamente.</p>}
    <button className="modal-btn-cancelar" type="button" disabled={salvando} onClick={onFechar}>Fechar e atualizar agenda</button>
  </section></div>;
}
