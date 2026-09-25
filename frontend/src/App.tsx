import { useState } from 'react';
import logoImg from './assets/logo.png'; // Importação da sua imagem PNG
import './App.css';

export function App() {
  const [emailOuTelefone, setEmailOuTelefone] = useState('');
  const [senha, setSenha] = useState('');
  const [mostrarSenha, setMostrarSenha] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    alert(`Entrando com: ${emailOuTelefone}`);
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
  
  {/* descrição, mudar no futuro talvez */}
  <h2 className="brand-subtitle">BARBEARIA</h2>
  <p className="brand-tagline">Desde 2019</p>
</div>

      {/* lado direito */}
      <div className="login-card">
        <h2 className="card-title">Login</h2>
        <p className="card-subtitle">Entre na sua conta para continuar.</p>

        <form onSubmit={handleSubmit} className="login-form">
          {/* campo email ou telefone */}
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

          {/* esqueci minha senha */}
          <div className="forgot-password-wrapper">
            <a href="#esqueci" className="forgot-password-link">
              Esqueceu sua senha?
            </a>
          </div>

          {/* entrar */}
          <button type="submit" className="btn-submit">
            Entrar
          </button>
        </form>

        {/* divisora */}
        <div className="divider">
          <span>Ou</span>
        </div>

        {/* google */}
        <button type="button" className="btn-google">
          <svg width="18" height="18" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
          </svg>
          Entrar com Google
        </button>

        {/* link pra página de cadastro */}
        <div className="signup-wrapper">
          <span>Não tem uma conta? </span>
          <a href="#cadastre-se" className="signup-link">
            Cadastre-se.
          </a>
        </div>
      </div>
    </div>
  );
}

export default App;