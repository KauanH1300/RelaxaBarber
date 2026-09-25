import { Link } from 'react-router-dom';
import { useState } from 'react';
import logoImg from './assets/logo.png';
import './App.css'; //importando o mesmo css

export function Cadastro() {
  const [nome, setNome] = useState('');
  const [emailOuTelefone, setEmailOuTelefone] = useState('');
  const [senha, setSenha] = useState('');
  const [mostrarSenha, setMostrarSenha] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    alert(`Cadastrando:\nNome: ${nome}\nContato: ${emailOuTelefone}`);
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
        <h2 className="card-title">Cadastro</h2>
        <p className="card-subtitle">Crie sua conta para agendar seus horários.</p>

        <form onSubmit={handleSubmit} className="login-form">
          {/* campo do nome */}
          <div className="input-box">
            <span className="input-icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#818e9b" strokeWidth="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </span>
            <input
              type="text"
              placeholder="Nome Completo"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              required
            />
          </div>

          {/* campo do email e telefone */}
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
              value={emailOuTelefone}
              onChange={(e) => setEmailOuTelefone(e.target.value)}
              required
            />
          </div>

          {/* campo da senha */}
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

          {/* cadastrar */}
          <button type="submit" className="btn-submit" style={{ marginTop: '12px' }}>
            Cadastrar
          </button>
        </form>

            <div className="signup-wrapper">
            <span>Já tem uma conta? </span>
            <Link to="/login" className="signup-link">
             Entrar.
            </Link>
            </div>
      </div>
    </div>
  );
}

export default Cadastro;