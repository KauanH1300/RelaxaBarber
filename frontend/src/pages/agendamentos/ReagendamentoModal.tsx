import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { consultarReagendamento, salvarReagendamento, podeReagendar, localizarReagendamentoConfirmado } from '../../services/reagendamento';
import type { DadosReagendamento, ReservaReagendamento, HistoricoReagendamento } from '../../services/reagendamento';
import type { ProfissionalAgenda, UsuarioAgenda } from '../../services/permissoesAgenda';
import { mensagemErro, escritaAgendaIncerta } from '../../services/erros';
import { SugestoesAgenda } from './SugestoesAgenda';

interface Props {
  agendamentoId: string; usuario: UsuarioAgenda; barbeiros: ProfissionalAgenda[];
  onFechar: () => void; onSalvo: (data: string) => void; onConferir: () => void;
}

export function ReagendamentoModal({ agendamentoId, usuario, barbeiros, onFechar, onSalvo, onConferir }: Props) {
  const [marca] = useState(contextoAtual);
  const [reserva, setReserva] = useState<ReservaReagendamento | null>(null);
  const [historico, setHistorico] = useState<HistoricoReagendamento[]>([]);
  const [data, setData] = useState(''); const [hora, setHora] = useState('');
  const [duracao, setDuracao] = useState('');
  const [barbeiroId, setBarbeiroId] = useState(''); const [motivo, setMotivo] = useState('');
  const [erro, setErro] = useState(''); const [salvando, setSalvando] = useState(false);
  const [pendente, setPendente] = useState<DadosReagendamento | null>(null);
  const [revisao, setRevisao] = useState<ReservaReagendamento | null>(null);
  const [revalidar, setRevalidar] = useState(false);
  const [tentativaCarga, setTentativaCarga] = useState(0);
  const enviando = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    consultarReagendamento(agendamentoId, marca, controller.signal).then(({ reserva: r, historico: h }) => {
      if (!controller.signal.aborted && contextoValido(marca)) {
        setReserva(r); setHistorico(h); setData(r.data); setHora(r.hora_inicio); setBarbeiroId(r.barbeiro_id);
      }
    }).catch(e => { if (!controller.signal.aborted && contextoValido(marca)) setErro(mensagemErro(e, 'Não foi possível consultar o atendimento')); });
    return () => controller.abort();
  }, [agendamentoId, marca, tentativaCarga]);

  async function conferir(antes: ReservaReagendamento, dados: DadosReagendamento | null) {
    try {
      const atual = await consultarReagendamento(agendamentoId, marca);
      if (!contextoValido(marca)) return;
      if (dados && localizarReagendamentoConfirmado(atual.historico, historico, antes, dados, usuario)) {
        onSalvo(atual.reserva.data);
        return;
      }
      setRevalidar(false);
      setPendente(null);
      setHistorico(atual.historico);
      if (atual.reserva.atualizado_em !== antes.atualizado_em || atual.reserva.status !== antes.status) {
        setRevisao(atual.reserva);
      }
    } catch (falha) {
      if (contextoValido(marca)) setErro(mensagemErro(falha, 'Não foi possível conferir o atendimento'));
    }
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (enviando.current || revisao || revalidar || !reserva) return;
    const dados = pendente ?? { data, hora_inicio: hora, barbeiro_id: barbeiroId, motivo,
      duracao_min: duracao ? Number(duracao) : undefined };
    enviando.current = true; setSalvando(true); setErro('');
    try {
      const resultado = await salvarReagendamento(reserva, dados, usuario, marca);
      if (contextoValido(marca)) onSalvo(resultado.data);
    } catch (falha) {
      if (!contextoValido(marca)) return;
      const incerto = escritaAgendaIncerta(falha);
      const status = axios.isAxiosError(falha) ? falha.response?.status : undefined;
      if (incerto) setPendente(dados);
      else setErro(!axios.isAxiosError(falha) && falha instanceof Error ? falha.message :
        mensagemErro(falha, 'O reagendamento foi rejeitado. Revise data, horário e barbeiro.'));
      if (incerto || status === 409) onConferir();
      if (status === 409 || (pendente && status === 422)) {
        setRevalidar(true);
        await conferir(reserva, pendente);
      }
    } finally { enviando.current = false; setSalvando(false); }
  }
  const permitido = reserva && podeReagendar(usuario, reserva.barbeiro_id, reserva.status);
  const profissional = (id: string) => barbeiros.find(b => b.id === id)?.nome ?? id;
  const dia = (d: string) => d.split('-').reverse().join('/');
  return <div className="modal-overlay"><section className="modal-box reagendamento-modal" role="dialog" aria-modal="true" aria-labelledby="reagendamento-titulo">
    <h2 id="reagendamento-titulo">Reagendar atendimento</h2>
    {erro && <p role="alert" className="modal-erro">{erro}</p>}
    {!reserva && !erro && <p role="status">Carregando atendimento…</p>}
    {!reserva && erro && <button type="button" onClick={() => { setErro(''); setTentativaCarga(n => n + 1); }}>Tentar carregar novamente</button>}
    {reserva && <>
      <p>{reserva.cliente.nome} — {dia(reserva.data)} às {reserva.hora_inicio.slice(0, 5)}, {reserva.barbeiro.nome}</p>
      {!permitido && <p role="alert">Este atendimento não pode ser reagendado pelo seu perfil ou estado atual.</p>}
      <form onSubmit={e => void salvar(e)}><fieldset disabled={salvando || !!pendente || !!revisao || revalidar || !permitido}>
        <legend>Novo horário e profissional</legend>
        <label className="modal-campo">Data<input required type="date" value={data} onChange={e => setData(e.target.value)} /></label>
        <label className="modal-campo">Horário<input required type="time" step="1" value={hora} onChange={e => setHora(e.target.value)} /></label>
        <label className="modal-campo">Barbeiro<select required value={barbeiroId} onChange={e => setBarbeiroId(e.target.value)}><option value="">Selecione…</option>{barbeiros.map(b => <option key={b.id} value={b.id}>{b.nome}</option>)}</select></label>
        <label className="modal-campo">Motivo (opcional)<input maxLength={1000} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
        <label className="modal-campo">Duração total em minutos (opcional)
          <input type="number" min={1} max={480} step={1} value={duracao} onChange={e => setDuracao(e.target.value)} />
        </label>
        <p>Deixe a duração em branco para manter a atual. Os serviços e preços são preservados.</p>
        <SugestoesAgenda key={JSON.stringify([data, duracao, reserva.atualizado_em, erro])}
          marca={marca} data={data} duracao={duracao ? Number(duracao) : undefined} agendamentoId={agendamentoId}
          onEscolher={s => { setHora(s.hora_inicio); setBarbeiroId(s.barbeiro_id); setErro(''); }} />
      </fieldset>
        {salvando && <p role="status">{pendente || revalidar ? 'Conferindo reagendamento…' : 'Reagendando…'}</p>}
        {pendente && <p role="status">O resultado ainda não foi confirmado. Você pode confirmar a mesma alteração.</p>}
        <button className="modal-btn-salvar" type="submit" disabled={salvando || !!revisao || revalidar || !permitido}>
          {pendente ? 'Confirmar mesma alteração' : 'Confirmar reagendamento'}
        </button>
      </form>
      {revalidar && !salvando && <button type="button" onClick={async () => {
        if (enviando.current) return;
        enviando.current = true; setSalvando(true); setErro('');
        try { await conferir(reserva, pendente); } finally { enviando.current = false; setSalvando(false); }
      }}>Consultar atendimento atualizado</button>}
      {revisao && <div role="status">
        <p>O atendimento foi alterado. Confira o horário atual antes de reenviar. Seus dados continuam preenchidos.</p>
        <p>{dia(revisao.data)} às {revisao.hora_inicio.slice(0, 5)}–{revisao.hora_fim.slice(0, 5)}, {revisao.barbeiro.nome} ({revisao.status})</p>
        <button type="button" onClick={() => { setReserva(revisao); setRevisao(null); setErro(''); }}>Revisar meus dados</button>
      </div>}
      <details><summary>Histórico de reagendamentos ({historico.length})</summary>
        {!historico.length && <p>Nenhum reagendamento registrado.</p>}
        <ul>{historico.map(h => <li key={h.id}>{dia(h.data_anterior)} {h.hora_inicio_anterior.slice(0, 5)}–{h.hora_fim_anterior?.slice(0, 5) || '—'} ({profissional(h.barbeiro_id_anterior)}) → {dia(h.data_nova)} {h.hora_inicio_nova.slice(0, 5)}–{h.hora_fim_nova?.slice(0, 5) || '—'} ({profissional(h.barbeiro_id_novo)}). {h.motivo}</li>)}</ul>
      </details>
    </>}
    <button className="modal-btn-cancelar" type="button" disabled={salvando} onClick={() => {
      if (!pendente || window.confirm('O resultado continua incerto. Fechar e conferir a agenda?')) onFechar();
    }}>Fechar e atualizar agenda</button>
  </section></div>;
}
