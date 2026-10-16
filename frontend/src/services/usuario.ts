import { useOutletContext } from 'react-router-dom';
import type { PerfilAgenda } from './permissoesAgenda';

export interface UsuarioLogado {
  id: string;
  nome: string;
  email: string;
  telefone: string | null;
  perfil: PerfilAgenda;
  ativo: boolean;
  data_cadastro: string;
}

export const nomesPerfil: Record<PerfilAgenda, string> = {
  admin: 'Administrador', recepcao: 'Recepção', barbeiro: 'Barbeiro', barbeiro_chefe: 'Barbeiro-chefe',
};

export function useUsuario(): UsuarioLogado {
  return useOutletContext<{ usuario: UsuarioLogado }>().usuario;
}

export function podeGerenciarServicos(usuario: Pick<UsuarioLogado, 'perfil'>): boolean {
  return usuario.perfil === 'admin';
}
