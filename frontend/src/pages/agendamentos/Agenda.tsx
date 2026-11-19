import { useState, useEffect, useRef } from 'react';
import api from '../../services/api';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { mensagemErro, deveConferirRegistros, escritaIncerta } from '../../services/erros';
import { dataLocal, horariosAgenda } from '../../services/agenda';
import { useUsuario } from '../../services/usuario';
import { podeOperarAgenda, profissionaisParaCriacao, podeCancelarAgendamento } from '../../services/permissoesAgenda';
import rodrigoImg from '../../assets/rodrigo_relaxa.png';
import higorImg from '../../assets/higor_rodrigo.png';
import './Agenda.css';
import { NovoAgendamentoModal } from './NovoAgendamentoModal';
import { ReagendamentoModal } from './ReagendamentoModal';
import { CancelamentoAgendamentoModal } from './CancelamentoAgendamentoModal';
import { podeReagendar } from '../../services/reagendamento';

interface Agendamento {
  id: string;
  horario: string;
  termino: string;
  terminoCompleto: string;
  cliente: string;
  servico: string;
  contato: string;
  barbeiroId: string;
  statusColor: string;
  versao: string | null;
  faltaMotivo: string | null;
  faltaData: string | null;
  faltaAutor: string | null;
  status: string;
}
interface AgendamentoApi {
  id: string;
  hora_inicio: string;
  hora_fim: string;
  atualizado_em?: string | null;
  falta_motivo?: string | null;
  falta_registrada_em?: string | null;
  falta_registrada_por?: string | null;
  status: string;
  cliente: { nome: string; telefone: string };
  barbeiro: { id: string; nome: string };
  servicos: { servico: { nome: string } }[];
}

const COR_STATUS: Record<string, string> = {
  pendente: '#d4e157',
  aguardando: '#1e88e5', 
  em_atendimento: '#e53935',
  concluido: '#388e3c',
};

export function Agenda() {
  const [dataAtual, setDataAtual] = useState<Date>(new Date());
  const [modalAberto, setModalAberto] = useState(false);
  const [reagendando, setReagendando] = useState<string | null>(null);
  const [cancelamento, setCancelamento] = useState<{ id: string; historico: boolean } | null>(null);
  const [incluirCancelados, setIncluirCancelados] = useState(false);
  const [sucesso, setSucesso] = useState('');
  const [falta, setFalta] = useState<{ id: string; motivo: string } | null>(null);
  const usuario = useUsuario();
  const [carregandoAgenda, setCarregandoAgenda] = useState(true);
  const [erroProfissionais, setErroProfissionais] = useState('');
  const [tentativaProfissionais, setTentativaProfissionais] = useState(0);
  const [erroAgenda, setErroAgenda] = useState('');
  const [erroAcao, setErroAcao] = useState('');
  const [alterando, setAlterando] = useState(false);
  const atualizando = useRef(false);
  const [recarregar, setRecarregar] = useState(0);
  interface Barbeiro {
  id: string;
  nome: string;
}

const FOTOS: Record<string, string> = {
  'Rodrigo Relaxa': rodrigoImg,
  'Higor Rodrigo': higorImg,
};
const [barbeiros, setBarbeiros] = useState<Barbeiro[]>([]);

useEffect(() => {
  let ativo = true;
  api.get<Barbeiro[]>('/usuarios/barbeiros').then((profissionais) => {
    if (!ativo) return;
    setBarbeiros(profissionais.data);
    setErroProfissionais('');
  }).catch((falha: unknown) => {
    if (!ativo) return;
    setBarbeiros([]);
    setErroProfissionais(mensagemErro(falha, 'Não foi possível carregar os profissionais'));
  });
  return () => { ativo = false; };
}, [tentativaProfissionais]);

  const barbeirosCriacao = profissionaisParaCriacao(usuario, barbeiros);

  const [agendamentos, setAgendamentos] = useState<Agendamento[]>([]);

useEffect(() => {
  let ativo = true;
  const dia = dataLocal(dataAtual); // formato AAAA-MM-DD

  api
    .get<AgendamentoApi[]>('/agendamentos', { params: { data: dia, incluir_cancelados: incluirCancelados } })
    .then((resposta) => {
      if (!ativo) return;
      setErroAgenda('');
      setAgendamentos(
        resposta.data.map((a) => ({
          id: a.id,
          horario: a.hora_inicio.slice(0, 5),
          termino: a.hora_fim.slice(0, 5),
          terminoCompleto: a.hora_fim,
          cliente: a.cliente.nome,
          servico:
            a.servicos.length > 1
              ? `${a.servicos[0].servico.nome} + ${a.servicos.length - 1} Serviços`
              : a.servicos[0]?.servico.nome ?? '',
          contato: a.cliente.telefone,
          barbeiroId: a.barbeiro.id,
          status: a.status,
          versao: a.atualizado_em ?? null,
          faltaMotivo: a.falta_motivo ?? null,
          faltaData: a.falta_registrada_em ?? null,
          faltaAutor: a.falta_registrada_por ?? null,
          statusColor: COR_STATUS[a.status] ?? '#757575',
        }))
      );
    })
    .catch((falha: unknown) => {
      if (!ativo) return;
      setAgendamentos([]);
      setErroAgenda(mensagemErro(falha, 'Não foi possível carregar os agendamentos'));
    }).finally(() => { if (ativo) setCarregandoAgenda(false); });
  return () => { ativo = false; };
}, [dataAtual, recarregar, incluirCancelados]);

  const gradeHorarios = horariosAgenda(agendamentos.map((item) => item.horario));

  const formatarDataExibicao = (date: Date) =>
    date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });

  const MudarDia = (dias: number) => {
    const novaData = new Date(dataAtual);
    novaData.setDate(novaData.getDate() + dias);
    setCarregandoAgenda(true);
    setDataAtual(novaData);
  };

  const obterAgendamentosDoBlocoEBarbeiro = (horarioBloco: string, barbeiroId: string) => {
    const [horaBloco, minBloco] = horarioBloco.split(':').map(Number);
    const inicioBlocoEmMinutos = horaBloco * 60 + minBloco;
    const fimBlocoEmMinutos = inicioBlocoEmMinutos + 30;

    return agendamentos.filter((item) => {
      const [horaItem, minItem] = item.horario.split(':').map(Number);
      const itemEmMinutos = horaItem * 60 + minItem;

      const mesmoBarbeiro = item.barbeiroId.toLowerCase().trim() === barbeiroId.toLowerCase().trim();
      const noIntervalo = itemEmMinutos >= inicioBlocoEmMinutos && itemEmMinutos < fimBlocoEmMinutos;

      return mesmoBarbeiro && noIntervalo;
    });
  };
  const PROXIMO_STATUS: Record<string, string> = {
  pendente: 'aguardando',
  aguardando: 'em_atendimento',
  em_atendimento: 'concluido',
};

function recarregarAgenda(dia?: string) {
  if (dia && dia !== dataLocal(dataAtual)) {
    const [ano, mes, data] = dia.split('-').map(Number);
    setDataAtual(new Date(ano, mes - 1, data, 12));
  }
  setCarregandoAgenda(true);
  setRecarregar((n) => n + 1);
}

const trocarStatus = async (item: Agendamento, motivoFalta?: string) => {
  const novo = motivoFalta === undefined ? PROXIMO_STATUS[item.status] : 'nao_compareceu';
  if (!podeOperarAgenda(usuario, item.barbeiroId) || !novo || atualizando.current || carregandoAgenda) return;
  const contexto = contextoAtual();
  atualizando.current = true;
  setAlterando(true);
  setErroAcao('');
  try {
    const dados = motivoFalta === undefined ? { status: novo } : {
      status: novo, falta_motivo: motivoFalta, confirmado: true, atualizado_em_esperado: item.versao,
    };
    await api.patch(`/agendamentos/${item.id}/status`, dados, { params: { filial_id: contexto.filialId } });
    if (!contextoValido(contexto)) return;
    if (motivoFalta !== undefined) { setFalta(null); setSucesso('Não comparecimento registrado.'); }
    recarregarAgenda();
  } catch (e: unknown) {
    if (!contextoValido(contexto)) return;
    setErroAcao(mensagemErro(e, 'Erro ao alterar agendamento') + (escritaIncerta(e) ? ' Confira a agenda antes de repetir a operação.' : ''));
    if (deveConferirRegistros(e)) recarregarAgenda();
  } finally {
    atualizando.current = false;
    setAlterando(false);
  }
};
  return (
    <div className="agenda-content">
      <div className="agenda-top-bar">
        <div>
          <h1 className="agenda-title">Agenda</h1>
        </div>

        <div className="agenda-actions">
          <button className="btn-bloquear" disabled title="Funcionalidade ainda indisponível">Bloquear Horários</button>
          <button className="btn-novo" disabled={barbeirosCriacao.length === 0} onClick={() => setModalAberto(true)}>
            Novo agendamento
          </button>
          <div className="date-picker-badge">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
            <span>{formatarDataExibicao(dataAtual)}</span>
            <span className="chevron">
              <button type="button" onClick={() => MudarDia(-1)} className="arrow-btn" title="Dia anterior">
                &lt;
              </button>
              <button type="button" onClick={() => MudarDia(1)} className="arrow-btn" title="Próximo dia">
                &gt;
              </button>
            </span>
          </div>
        </div>
      </div>

      {carregandoAgenda && <p role="status">Carregando agenda...</p>}
      {erroProfissionais && <><p role="alert">{erroProfissionais}</p><button type="button" onClick={() => setTentativaProfissionais((n) => n + 1)}>Recarregar profissionais</button></>}
      {erroAgenda && <p role="alert">{erroAgenda}</p>}
      <button type="button" disabled={carregandoAgenda || alterando} onClick={() => recarregarAgenda()}>Atualizar agenda</button>
      <label><input type="checkbox" checked={incluirCancelados} disabled={alterando || carregandoAgenda} onChange={event => { setCarregandoAgenda(true); setIncluirCancelados(event.target.checked); }} />Incluir agendamentos cancelados</label>
      {erroAcao && <p role="alert">{erroAcao}</p>}
      {sucesso && <p role="status">{sucesso}</p>}
      {/* cabeçalho barbeiros */}
      <div className="barbers-header-row">
        <div className="time-label-header">Horário</div>
        <div className="barber-columns-header">
          {barbeiros.map((barbeiro) => (
            <div key={barbeiro.id} className="barber-column-title">
    <div className="barber-avatar">
      {FOTOS[barbeiro.nome] ? (
        <img src={FOTOS[barbeiro.nome]} alt={barbeiro.nome} className="barber-photo" />
      ) : (
        <span>{barbeiro.nome[0]}</span>
      )}
    </div>
    <span>{barbeiro.nome}</span>
  </div>
          ))}
        </div>
      </div>

      {/* horários */}
      <div className="timeline-container">
        {gradeHorarios.map((horarioBloco) => (
          <div key={horarioBloco} className="time-row">
            <span className="time-label">{horarioBloco}</span>
            <div className="barber-slots-container">
              {barbeiros.map((barbeiro) => {
                const agendamentosDoBarbeiro = obterAgendamentosDoBlocoEBarbeiro(horarioBloco, barbeiro.id);

                return (
                  <div key={barbeiro.id} className="time-slot">
                    {agendamentosDoBarbeiro.map((item) => (
                      <div
                        key={item.id}
                        className="appointment-card"
                        style={{ borderLeftColor: item.statusColor }}
                      >
                        <div className="card-header-info">
                          <strong className="card-title-text">
                            {item.horario}–{item.termino} - {item.cliente}
                          </strong>
                        </div>
                        <p className="card-service">{item.servico}</p>
                        <p className="card-contact">{item.contato}</p>
                        {item.status === 'cancelado' && <><p>Cancelado</p><button type="button" onClick={() => setCancelamento({ id: item.id, historico: true })}>Consultar histórico</button></>}
                        {item.status === 'nao_compareceu' && <details><summary>Não compareceu</summary>
                          <p>{item.faltaMotivo}</p>
                          <p>{item.faltaData && new Date(item.faltaData).toLocaleString('pt-BR', { timeZone: 'America/Recife' })}</p>
                          <p>Responsável: {item.faltaAutor}</p>
                        </details>}
                        {item.status === 'pendente' && item.versao && ['admin', 'recepcao'].includes(usuario.perfil)
                          && Date.parse(`${dataLocal(dataAtual)}T${item.terminoCompleto}-03:00`) <= Date.now() &&
                          (falta?.id === item.id ? <form onSubmit={e => { e.preventDefault(); if (falta.motivo.trim()) void trocarStatus(item, falta.motivo.trim()); }}>
                            <label>Motivo do não comparecimento<input required maxLength={1000} value={falta.motivo}
                              onChange={e => setFalta({ id: item.id, motivo: e.target.value })} /></label>
                            <button disabled={alterando || carregandoAgenda}>Confirmar falta</button>
                            <button type="button" onClick={() => setFalta(null)}>Voltar</button>
                          </form> : <button type="button" disabled={alterando || carregandoAgenda} onClick={() => setFalta({ id: item.id, motivo: '' })}>Registrar falta</button>)}
                        {podeReagendar(usuario, item.barbeiroId, item.status) && <button type="button" disabled={alterando || carregandoAgenda || !!reagendando} onClick={() => { setSucesso(''); setReagendando(item.id); }}>Reagendar</button>}
                        {podeOperarAgenda(usuario, item.barbeiroId) && PROXIMO_STATUS[item.status] && (
                          <div>
                            <button type="button" disabled={alterando || carregandoAgenda} onClick={() => trocarStatus(item)}>
                              {item.status === 'pendente' ? 'Registrar chegada' : item.status === 'aguardando' ? 'Iniciar atendimento' : 'Concluir atendimento'}
                            </button>
                            {podeCancelarAgendamento(item.status) && (
                              <button type="button" disabled={alterando || carregandoAgenda} onClick={() => { setSucesso(''); setCancelamento({ id: item.id, historico: false }); }}>
                                Cancelar agendamento
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      {cancelamento && <CancelamentoAgendamentoModal key={cancelamento.id} agendamentoId={cancelamento.id} historico={cancelamento.historico} usuario={usuario}
        onFechar={() => { setCancelamento(null); recarregarAgenda(); }} onConferir={() => recarregarAgenda()}
        onSalvo={() => { setCancelamento(null); setSucesso('Agendamento cancelado. O histórico foi preservado.'); recarregarAgenda(); }} />}
      {reagendando && <ReagendamentoModal key={reagendando} agendamentoId={reagendando} usuario={usuario} barbeiros={barbeirosCriacao}
        onFechar={() => { setReagendando(null); recarregarAgenda(); }} onConferir={() => recarregarAgenda()}
        onSalvo={dia => { setReagendando(null); setSucesso('Atendimento reagendado com sucesso.'); recarregarAgenda(dia); }} />}
       {modalAberto && <NovoAgendamentoModal dataInicial={dataLocal(dataAtual)} aberto={modalAberto} onFechar={() => setModalAberto(false)} onConferir={recarregarAgenda} onSalvo={(dia) => {
    setModalAberto(false);
    recarregarAgenda(dia);
  }}barbeiros={barbeirosCriacao} />}
    </div>
  );
}

export default Agenda;
