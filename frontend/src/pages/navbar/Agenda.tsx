import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import logoImg from '../../assets/logo.png';
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
  const navigate = useNavigate();

  const [dataAtual, setDataAtual] = useState<Date>(new Date(2026, 8, 15));
  const [abaAtiva, setAbaAtiva] = useState('agendamentos');

  // barbeiros
  const barbeiros = [
    { nome: 'Rodrigo Relaxa', foto: rodrigoImg },
    { nome: 'Higor Rodrigo', foto: higorImg }
  ];

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
      barbeiro: 'Higor Rodrigo',
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

  const formatarDataExibicao = (date: Date) => {
    return date.toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: 'long',
      year: 'numeric'
    });
  };

  const MudarDia = (dias: number) => {
    const novaData = new Date(dataAtual);
    novaData.setDate(novaData.getDate() + dias);
    setDataAtual(novaData);
  };

  const handleNavegacao = (abaKey: string, rota?: string) => {
    setAbaAtiva(abaKey);
    if (rota) {
      navigate(rota);
    }
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
    <div className="dashboard-layout">
      {/* header */}
      <header className="dashboard-header">
        <div className="header-brand">
          <img src={logoImg} alt="Relaxa Barbearia" className="header-logo" />
        </div>

        <div className="header-user-menu">
          <button className="icon-btn" title="Notificações">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" />
            </svg>
          </button>

          <div className="user-profile">
            <div className="avatar-placeholder">ADM</div>
            <div className="user-info">
              <span className="user-name">Conta ADM</span>
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M7 10l5 5 5-5z" />
            </svg>
          </div>
        </div>
      </header>

      <div className="dashboard-body">
        {/* navbar/sidebar */}
        <nav className="sidebar-nav-expanded">
          <div className="sidebar-group">
            <button
              className={`sidebar-item ${abaAtiva === 'agendamentos' ? 'active' : ''}`}
              onClick={() => handleNavegacao('agendamentos', '/agenda')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
              <span>Agendamentos</span>
            </button>

            <button
              className={`sidebar-item ${abaAtiva === 'comandas' ? 'active' : ''}`}
              onClick={() => handleNavegacao('comandas', '/comandas')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
                <polyline points="10 9 9 9 8 9" />
              </svg>
              <span>Comandas</span>
            </button>

            <button
              className={`sidebar-item ${abaAtiva === 'comissoes' ? 'active' : ''}`}
              onClick={() => handleNavegacao('comissoes', '/comissoes')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="1" x2="12" y2="23" />
                <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
              <span>Comissões</span>
            </button>

            <button
              className={`sidebar-item ${abaAtiva === 'despesas' ? 'active' : ''}`}
              onClick={() => handleNavegacao('despesas', '/despesas')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
                <line x1="1" y1="10" x2="23" y2="10" />
              </svg>
              <span>Despesas</span>
            </button>

            <button
              className={`sidebar-item ${abaAtiva === 'dashboard' ? 'active' : ''}`}
              onClick={() => handleNavegacao('dashboard', '/dashboard')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="7" height="9" />
                <rect x="14" y="3" width="7" height="5" />
                <rect x="14" y="12" width="7" height="9" />
                <rect x="3" y="16" width="7" height="5" />
              </svg>
              <span>Dashboard</span>
            </button>

            <button
              className={`sidebar-item ${abaAtiva === 'servicos' ? 'active' : ''}`}
              onClick={() => handleNavegacao('servicos', '/servicos')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="6" cy="6" r="3" />
                <circle cx="6" cy="18" r="3" />
                <line x1="20" y1="4" x2="8.12" y2="15.88" />
                <line x1="14.47" y1="14.48" x2="20" y2="20" />
                <line x1="8.12" y1="8.12" x2="12" y2="12" />
              </svg>
              <span>Serviços</span>
            </button>

            <button
              className={`sidebar-item ${abaAtiva === 'itens' ? 'active' : ''}`}
              onClick={() => handleNavegacao('itens', '/itens')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
                <line x1="12" y1="22.08" x2="12" y2="12" />
              </svg>
              <span>Itens</span>
            </button>

            <button
              className={`sidebar-item ${abaAtiva === 'usuarios' ? 'active' : ''}`}
              onClick={() => handleNavegacao('usuarios', '/usuarios')}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              <span>Usuários</span>
            </button>
          </div>
        </nav>

        {/* corpo agenda */}
        <main className="agenda-content">
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
                  <button
                    type="button"
                    onClick={() => MudarDia(-1)}
                    className="arrow-btn"
                    title="Dia anterior"
                  >
                    &lt;
                  </button>
                  <button
                    type="button"
                    onClick={() => MudarDia(1)}
                    className="arrow-btn"
                    title="Próximo dia"
                  >
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
        </main>
      </div>
    </div>
  );
}

export default Agenda;