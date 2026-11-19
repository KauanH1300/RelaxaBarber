import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { podeGerenciarServicos, useUsuario } from '../services/usuario';

export function SomenteAdministrador({ children, mensagem = 'Sem permissão para gerenciar serviços.', retorno = '/servicos' }: { children: ReactNode; mensagem?: string; retorno?: string }) {
  const usuario = useUsuario();
  if (!podeGerenciarServicos(usuario)) {
    return <p role="alert">{mensagem} <Link to={retorno}>Voltar</Link></p>;
  }
  return children;
}
