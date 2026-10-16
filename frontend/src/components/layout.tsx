import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate, Navigate } from 'react-router-dom';
import { getMe, logout } from '../services/auth';
import { EVENTO_SESSAO, obterToken } from '../services/sessao';
import { mensagemErro } from '../services/erros';
import { nomesPerfil } from '../services/usuario';
import type { UsuarioLogado } from '../services/usuario';

const itensMenu = [
  { para: '/agendamentos', texto: 'Agendamentos', icone: 'calendar_today' },
  { para: '/servicos', texto: 'Serviços', icone: 'content_cut' },
  { para: '/perfil', texto: 'Meu perfil', icone: 'person' },
];

export function Layout() {
  const navigate = useNavigate();
  const [usuario, setUsuario] = useState<UsuarioLogado | null>(null);
  const [token, setToken] = useState(obterToken);
  const [erro, setErro] = useState('');
  const [tentativa, setTentativa] = useState(0);

  useEffect(() => {
    const atualizar = () => {
      const atual = obterToken();
      if (atual !== token) { setToken(atual); setUsuario(null); }
    };
    window.addEventListener(EVENTO_SESSAO, atualizar);
    window.addEventListener('storage', atualizar);
    return () => {
      window.removeEventListener(EVENTO_SESSAO, atualizar);
      window.removeEventListener('storage', atualizar);
    };
  }, [token]);

  useEffect(() => {
    if (!token) return;
    let ativo = true;
    getMe().then((dados) => {
      if (ativo && obterToken() === token) { setUsuario(dados); setErro(''); }
    }).catch((falha: unknown) => {
      if (ativo && obterToken() === token) setErro(mensagemErro(falha, 'Não foi possível validar sua sessão'));
    });
    return () => { ativo = false; };
  }, [token, tentativa]);

  function sair() {
    logout();
    navigate('/login', { replace: true });
  }

  if (!token) return <Navigate to="/login" replace />;
  if (!usuario) return (
    <main>
      {erro ? <><p role="alert">{erro}</p><button onClick={() => { setErro(''); setTentativa((n) => n + 1); }}>Tentar novamente</button></>
        : <p role="status">Validando sessão...</p>}
      <button onClick={sair}>Ir para login</button>
    </main>
  );

  return (
    <div className="min-h-screen bg-surface">
      <aside className="fixed left-0 top-0 z-50 flex h-screen w-72 flex-col bg-surface-container-low shadow-[0_1px_8px_rgba(0,0,0,0.3)]">
        <div className="flex h-20 items-center px-6">
          <h1 className="text-base font-semibold tracking-tight text-on-surface">
            RelaxaBarber
          </h1>
        </div>

        <p className="px-6 pb-1 pt-2 text-[10px] font-bold uppercase tracking-wider text-outline">
          Gerenciamento
        </p>

        <nav className="flex-1 space-y-1 overflow-y-auto px-4">
          {itensMenu.map((item) => (
            <NavLink
              key={item.para}
              to={item.para}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-[11px] font-semibold transition-all ${
                  isActive
                    ? 'bg-primary-container text-on-primary-container shadow-[0_0_0_1px_#d4af37]'
                    : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
                }`
              }
            >
              <span className="material-symbols-outlined text-[18px]">
                {item.icone}
              </span>
              <span>{item.texto}</span>
            </NavLink>
          ))}
        </nav>

        <div className="p-4">
          <div className="flex items-center justify-between rounded-xl bg-surface-container p-2 shadow-[0_1px_8px_rgba(0,0,0,0.2)]">
            <div className="flex min-w-0 items-center gap-2">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-container text-sm font-bold text-on-primary-container">
                {(usuario.nome || usuario.email).charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-on-surface">
                  {usuario.nome || usuario.email}
                </p>
                <p className="truncate text-[11px] text-outline">
                  {nomesPerfil[usuario.perfil]}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={sair}
              title="Sair"
              className="rounded p-1 text-outline transition-colors hover:bg-surface-container-high hover:text-error"
            >
              <span className="material-symbols-outlined text-[16px]">logout</span>
            </button>
          </div>
        </div>
      </aside>

      <main className="ml-72 min-h-screen p-6">
        <Outlet context={{ usuario }} />
      </main>
    </div>
  );
}