export type PerfilAgenda = 'admin' | 'recepcao' | 'barbeiro_chefe' | 'barbeiro';
export interface UsuarioAgenda { id: string; perfil: PerfilAgenda }
export interface ProfissionalAgenda { id: string; nome: string }

export function podeOperarAgenda(usuario: UsuarioAgenda | null, profissionalId: string): boolean {
  if (!usuario) return false;
  if (usuario.perfil === 'admin' || usuario.perfil === 'recepcao') return true;
  return (usuario.perfil === 'barbeiro' || usuario.perfil === 'barbeiro_chefe')
    && usuario.id === profissionalId;
}

export function profissionaisParaCriacao(
  usuario: UsuarioAgenda | null, profissionais: ProfissionalAgenda[],
): ProfissionalAgenda[] {
  return profissionais.filter((p) => podeOperarAgenda(usuario, p.id));
}
