import { useState } from 'react';
import rodrigoImg from '../../assets/rodrigo_relaxa.png';
import higorImg from '../../assets/higor_rodrigo.png';
import './Agenda.css';

interface Agendamento {
  id: number;
  horario: string;
  cliente: string;
  servico: string;
  contato: string;
  barbeiro: string;
  statusColor: string;
}

export function Agenda() {
  const [dataAtual, setDataAtual] = useState<Date>(new Date(2026, 8, 15));

  const barbeiros = [
    { nome: 'Rodrigo Relaxa', foto: rodrigoImg },
    { nome: 'Higor Rodrigo', foto: higorImg },
  ];

  const agendamentos: Agendamento[] = [
    { id: 1, horario: '09:10', cliente: 'João Silva', servico: 'Corte Social + Barba', contato: '99294-2815', barbeiro: 'Rodrigo Relaxa', statusColor: '#d32f2f' },
    { id: 2, horario: '09:50', cliente: 'Kauan Henrique', servico: 'Degradê + 2 Serviços', contato: 'kauan5henrique@gmail.com', barbeiro: 'Higor Rodrigo', statusColor: '#d32f2f' },
    { id: 3, horario: '10:40', cliente: 'Pedro Lima', servico: 'Designer de Barba', contato: '96894-1565', barbeiro: 'Higor Rodrigo', statusColor: '#d32f2f' },
    { id: 4, horario: '12:20', cliente: 'Carlos Mendes', servico: 'Barba Completa', contato: 'kauan5henrique@gmail.com', barbeiro: 'Rodrigo Relaxa', statusColor: '#d4e157' },
    { id: 5, horario: '14:30', cliente: 'Rafael Costa', servico: 'Corte Social', contato: '96894-1565', barbeiro: 'Rodrigo Relaxa', statusColor: '#388e3c' },
    { id: 6, horario: '16:00', cliente: 'André Oliveira', servico: 'Corte Degradê + Barba', contato: '96894-1565', barbeiro: 'Rodrigo Relaxa', statusColor: '#388e3c' },
  ];

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

  const obterAgendamentosDoBlocoEBarbeiro = (horarioBloco: string, nomeBarbeiro: string) => {
    const [horaBloco, minBloco] = horarioBloco.split(':').map(Number);
    const inicioBlocoEmMinutos = horaBloco * 60 + minBloco;
    const fimBlocoEmMinutos = inicioBlocoEmMinutos + 30;

    return agendamentos.filter((item) => {
      const [horaItem, minItem] = item.horario.split(':').map(Number);
      const itemEmMinutos = horaItem * 60 + minItem;

      const mesmoBarbeiro = item.barbeiro.toLowerCase().trim() === nomeBarbeiro.toLowerCase().trim();
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
            <div key={barbeiro.nome} className="barber-column-title">
              <div className="barber-avatar">
                <img src={barbeiro.foto} alt={barbeiro.nome} className="barber-photo" />
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
                const agendamentosDoBarbeiro = obterAgendamentosDoBlocoEBarbeiro(horarioBloco, barbeiro.nome);

                return (
                  <div key={barbeiro.nome} className="time-slot">
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