import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { podeGerenciarServicos, useUsuario } from '../services/usuario';

export function SomenteAdministrador({ children }: { children: ReactNode }) {
  const usuario = useUsuario();
  if (!podeGerenciarServicos(usuario)) {
    return <p role="alert">Sem permissão para gerenciar serviços. <Link to="/servicos">Voltar</Link></p>;
  }
  return children;
}
