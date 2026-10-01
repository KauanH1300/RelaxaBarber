import { useState } from 'react';
import logoImg from '../../assets/logo.png';
import './Agenda.css';

interface Agendamento {
  id: number;
  horario: string;
  cliente: string;
  servico: string;
  contato: string;
  barbeiro: string;
  statusColor: string; // cor da barra
}

export function Agenda() {
  const [dataSelecionada, setDataSelecionada] = useState('15 de Setembro - 2026');
  
  // exemplos de agendamentos já feitos
  const agendamentos: Agendamento[] = [
    {
      id: 1,
      horario: '09:10',
      cliente: 'João Silva',
      servico: 'Corte Social + Barba',
      contato: '99294-2815',
      barbeiro: 'Rodrigo Relaxa',
      statusColor: '#d32f2f' 
    },
    {
      id: 2,
      horario: '09:50',
      cliente: 'Kauan Henrique',
      servico: 'Degradê + 2 Serviços',
      contato: 'kauan5henrique@gmail.com',
      barbeiro: 'Higor Rodrigo',
      statusColor: '#d32f2f' 
    },
    {
      id: 3,
      horario: '10:40',
      cliente: 'Pedro Lima',
      servico: 'Designer de Barba',
      contato: '96894-1565',
      barbeiro: 'Outro Barbeiro',
      statusColor: '#d32f2f' 
    },
    {
      id: 4,
      horario: '12:20',
      cliente: 'Carlos Mendes',
      servico: 'Barba Completa',
      contato: 'kauan5henrique@gmail.com',
      barbeiro: 'Rodrigo Relaxa',
      statusColor: '#d4e157' 
    },
    {
      id: 5,
      horario: '14:30',
      cliente: 'Rafael Costa',
      servico: 'Corte Social',
      contato: '96894-1565',
      barbeiro: 'Rodrigo Relaxa',
      statusColor: '#388e3c'
    },
    {
      id: 6,
      horario: '16:00',
      cliente: 'André Oliveira',
      servico: 'Corte Degradê + Barba',
      contato: '96894-1565',
      barbeiro: 'Rodrigo Relaxa',
      statusColor: '#388e3c' 
    }
  ];

  const gradeHorarios = [
    '08:00', '08:30', '09:00', '09:30', '10:00', '10:30', 
    '11:00', '11:30', '12:00', '12:30', '13:00', '13:30', 
    '14:00', '14:30', '15:00', '15:30', '16:00', '16:30', 
    '17:00', '17:30', '18:00'
  ];

  return (
    <div className="dashboard-layout">
      {/* header */}
      <header className="dashboard-header">
        <div className="header-brand">
          <img src={logoImg} alt="Relaxa Barbearia" className="header-logo" />
        </div>

        <div className="header-user-menu">
          {/* icone notificação, provavelmente irei remover na versão final */}
          <button className="icon-btn" title="Notificações">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" />
            </svg>
          </button>

          {/* perfil do barbeiro / ADM */}
          {/* pensando em como deixar essa parte */}
          <div className="user-profile">
            <div className="avatar-placeholder">HR</div>
            <div className="user-info">
              <span className="user-name">Higor Rodrigo</span>
              <span className="user-role">Barbeiro</span>
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 10l5 5 5-5z"/>
            </svg>
          </div>
        </div>
      </header>

      <div className="dashboard-body">
        {/* navbar */}
        <nav className="sidebar-nav">
          <button className="nav-item active" title="Agenda">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </button>

          <button className="nav-item" title="Agendamentos">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          </button>

          <button className="nav-item" title="Horários">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </button>

          <button className="nav-item" title="Serviços">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="6" cy="6" r="3" />
              <circle cx="6" cy="18" r="3" />
              <line x1="20" y1="4" x2="8.12" y2="15.88" />
              <line x1="14.47" y1="14.48" x2="20" y2="20" />
              <line x1="8.12" y1="8.12" x2="12" y2="12" />
            </svg>
          </button>

          <button className="nav-item highlight" title="Relatórios">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z"/>
            </svg>
          </button>
        </nav>

        {/* corpo */}
        <main className="agenda-content">
          <div className="agenda-top-bar">
            <div>
              <h1 className="agenda-title">Agenda</h1>
              {/* provavelmente irei remover os meus agendamentos na versão final */}
              <p className="agenda-subtitle">Meus agendamentos:</p>
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
  <span>{dataSelecionada}</span>
  <span className="chevron">
    <button 
      type="button" 
      onClick={() => setDataSelecionada('14 de Setembro - 2026')}
      style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}
    >
      &lt;
    </button>
    <button 
      type="button" 
      onClick={() => setDataSelecionada('16 de Setembro - 2026')}
      style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}
    >
      &gt;
    </button>
  </span>
</div>
            </div>
          </div>

          {/* horários */}
          <div className="timeline-container">
            {gradeHorarios.map((horario) => {
            
              const agendamento = agendamentos.find(item => item.horario.startsWith(horario.slice(0, 2)));

              return (
                <div key={horario} className="time-row">
                  <span className="time-label">{horario}</span>
                  <div className="time-slot">
                    {agendamento && agendamento.horario === horario && (
                      <div 
                        className="appointment-card"
                        style={{ borderLeftColor: agendamento.statusColor }}
                      >
                        <div className="card-header-info">
                          <strong className="card-title-text">
                            {agendamento.horario} - {agendamento.cliente}
                          </strong>
                        </div>
                        <p className="card-service">{agendamento.servico}</p>
                        <p className="card-contact">{agendamento.contato}</p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </main>
      </div>
    </div>
  );
}

export default Agenda;