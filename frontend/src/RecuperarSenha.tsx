import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import logoImg from './assets/logo.png';
import './Login.css';

export function RecuperarSenha() {
  const [contato, setContato] = useState('');
  const [codigo, setCodigo] = useState('');
  const navigate = useNavigate();

  const handleEnviarCodigo = (e: React.FormEvent) => {
    e.preventDefault();
    alert(`Código enviado para: ${contato}`);
  };

  const handleConfirmarCodigo = (e: React.FormEvent) => {
    e.preventDefault();
    navigate('/nova-senha');
  };

  return (
    <div className="login-container">
      {/* lado esquerdo */}
      <div className="brand-section">
        <img 
          src={logoImg} 
          alt="Logo Relaxa Barbearia" 
          className="brand-logo-img" 
        />
        <h2 className="brand-subtitle">BARBEARIA</h2>
        <p className="brand-tagline">Desde 2019</p>
      </div>

      {/* lado direito */}
      <div className="login-card">
        <h2 className="card-title">Recuperação de Senha</h2>
        <p className="card-subtitle">
          Informe seu E-mail ou Número de Telefone para receber o código de recuperação.
        </p>

        <form onSubmit={handleEnviarCodigo} className="login-form">
          <div className="input-box">
            <span className="input-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818e9b" strokeWidth="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
            </span>
            <input
              type="text"
              placeholder="E-mail ou Telefone"
              value={contato}
              onChange={(e) => setContato(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn-submit">
            Enviar
          </button>
        </form>

        <p className="card-subtitle" style={{ marginTop: '24px', marginBottom: '12px' }}>
          Insira o código de verificação de 6 dígitos enviado para seu e-mail ou telefone.
        </p>

        <form onSubmit={handleConfirmarCodigo} className="login-form">
          <div className="input-box">
            <span className="input-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818e9b" strokeWidth="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
                <polyline points="22,6 12,13 2,6" />
              </svg>
            </span>
            <input
              type="text"
              placeholder="Código de 6 Dígitos"
              value={codigo}
              onChange={(e) => setCodigo(e.target.value)}
              maxLength={6}
              required
            />
          </div>

          <button type="submit" className="btn-submit">
            Confirmar
          </button>
        </form>
      </div>
    </div>
  );
}

export default RecuperarSenha;