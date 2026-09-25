import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import logoImg from './assets/logo.png';
import './App.css';

export function NovaSenha() {
  const [senha, setSenha] = useState('');
  const [confirmarSenha, setConfirmarSenha] = useState('');
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [mostrarConfirmar, setMostrarConfirmar] = useState(false);
  const navigate = useNavigate();

  const handleRedefinir = (e: React.FormEvent) => {
    e.preventDefault();
    if (senha !== confirmarSenha) {
      alert('As senhas não coincidem!');
      return;
    }
    alert('Senha alterada com sucesso!');
    navigate('/login');
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
        <h2 className="card-title">Criar nova senha</h2>
        <p className="card-subtitle">
          Crie uma nova senha para acesso a sua conta.
        </p>

        <form onSubmit={handleRedefinir} className="login-form">
          {/* campo da nova senha */}
          <div className="input-box">
            <span className="input-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818e9b" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </span>
            <input
              type={mostrarSenha ? 'text' : 'password'}
              placeholder="Senha"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setMostrarSenha(!mostrarSenha)}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818e9b" strokeWidth="2">
                {mostrarSenha ? (
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" />
                ) : (
                  <>
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </>
                )}
              </svg>
            </button>
          </div>

          {/* campo de confirmar senha */}
          <div className="input-box">
            <span className="input-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818e9b" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </span>
            <input
              type={mostrarConfirmar ? 'text' : 'password'}
              placeholder="Confirmar Nova Senha"
              value={confirmarSenha}
              onChange={(e) => setConfirmarSenha(e.target.value)}
              required
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setMostrarConfirmar(!mostrarConfirmar)}
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818e9b" strokeWidth="2">
                {mostrarConfirmar ? (
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" />
                ) : (
                  <>
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </>
                )}
              </svg>
            </button>
          </div>

          <button type="submit" className="btn-submit" style={{ marginTop: '12px' }}>
            Redefinir Senha
          </button>
        </form>
      </div>
    </div>
  );
}

export default NovaSenha;