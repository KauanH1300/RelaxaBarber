import { useState, useEffect } from 'react';
import api from '../../services/api';
import rodrigoImg from '../../assets/rodrigo_relaxa.png';
import higorImg from '../../assets/higor_rodrigo.png';
import './Agenda.css';

interface Agendamento {
  id: string;
  horario: string;
  cliente: string;
  servico: string;
  contato: string;
  barbeiroId: string;
  statusColor: string;
}
interface AgendamentoApi {
  id: string;
  hora_inicio: string;
  status: string;
  cliente: { nome: string; telefone: string };
  barbeiro: { id: string; nome: string };
  servicos: { servico: { nome: string } }[];
}

const COR_STATUS: Record<string, string> = {
  pendente: '#d4e157',
  confirmado: '#388e3c',
  concluido: '#757575',
};

export function Agenda() {
  const [dataAtual, setDataAtual] = useState<Date>(new Date());

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
  api
    .get<(Barbeiro & { perfil: string; ativo: boolean })[]>('/usuarios')
    .then((r) => setBarbeiros(r.data.filter((u) => u.perfil === 'barbeiro' && u.ativo)))
    .catch(() => setBarbeiros([]));
}, []);

  const [agendamentos, setAgendamentos] = useState<Agendamento[]>([]);

useEffect(() => {
  const dia = dataAtual.toLocaleDateString('en-CA'); // formato AAAA-MM-DD

  api
    .get<AgendamentoApi[]>('/agendamentos', { params: { data: dia } })
    .then((resposta) => {
      setAgendamentos(
        resposta.data.map((a) => ({
          id: a.id,
          horario: a.hora_inicio.slice(0, 5),
          cliente: a.cliente.nome,
          servico:
            a.servicos.length > 1
              ? `${a.servicos[0].servico.nome} + ${a.servicos.length - 1} Serviços`
              : a.servicos[0]?.servico.nome ?? '',
          contato: a.cliente.telefone,
          barbeiroId: a.barbeiro.id,
          statusColor: COR_STATUS[a.status] ?? '#757575',
        }))
      );
    })
    .catch(() => setAgendamentos([]));
}, [dataAtual]);

  const gradeHorarios = [
    '08:00', '08:30', '09:00', '09:30', '10:00', '10:30',
    '11:00', '11:30', '12:00', '12:30', '13:00', '13:30',
    '14:00', '14:30', '15:00', '15:30', '16:00', '16:30',
    '17:00', '17:30', '18:00',
  ];

  const formatarDataExibicao = (date: Date) =>
    date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' });

  const MudarDia = (dias: number) => {
    const novaData = new Date(dataAtual);
    novaData.setDate(novaData.getDate() + dias);
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

  return (
    <div className="agenda-content">
      <div className="agenda-top-bar">
        <div>
          <h1 className="agenda-title">Agenda</h1>
        </div>

        <div className="agenda-actions">
          <button className="btn-bloquear">Bloquear Horários</button>

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
                            {item.horario} - {item.cliente}
                          </strong>
                        </div>
                        <p className="card-service">{item.servico}</p>
                        <p className="card-contact">{item.contato}</p>
                      </div>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Agenda;