import { NavLink, Outlet } from 'react-router-dom';
import './layout.css';

const itensMenu = [
  { para: '/agendamentos', texto: 'Agendamentos' },
  { para: '/comandas', texto: 'Comandas' },
  { para: '/servicos', texto: 'Serviços' },
  { para: '/itens', texto: 'Itens' },
  { para: '/pagamentos', texto: 'Pagamentos' },
  { para: '/despesas', texto: 'Despesas' },
  { para: '/dashboard', texto: 'Dashboard' },
  { para: '/usuarios', texto: 'Usuários' },
];

export function Layout() {
  return (
    <div className="layout">
      <aside className="layout-menu">
        <h1 className="layout-logo">RelaxaBarber</h1>
        <nav>
          {itensMenu.map((item) => (
            <NavLink
              key={item.para}
              to={item.para}
              className={({ isActive }) =>
                isActive ? 'menu-link ativo' : 'menu-link'
              }
            >
              {item.texto}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="layout-conteudo">
        <Outlet />
      </main>
    </div>
  );
}