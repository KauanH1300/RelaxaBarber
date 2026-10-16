export interface Filial { id: string; nome: string; fuso_horario: string }
export interface MarcaContexto { versao: number; token: string | null; filialId: string | null }
export const EVENTO_ACESSO_FILIAIS = 'relaxabarber:acesso-filiais';
let atual: MarcaContexto = { versao: 0, token: null, filialId: null };

export function contextoAtual(): MarcaContexto { return { ...atual }; }
export function mudarContexto(token: string | null, filialId: string | null): MarcaContexto {
  atual = { versao: atual.versao + 1, token, filialId };
  return contextoAtual();
}
export function contextoValido(marca: MarcaContexto): boolean {
  return marca.versao === atual.versao && marca.token === atual.token && marca.filialId === atual.filialId;
}
export function filialRestauravel(filiais: Filial[], preferida: string | null): string | null {
  if (filiais.length === 1) return filiais[0].id;
  return filiais.some((f) => f.id === preferida) ? preferida : null;
}
export function lerPreferencia(usuarioId: string): string | null {
  try { return localStorage.getItem(`relaxabarber:filial:${usuarioId}`); } catch { return null; }
}
export function salvarPreferencia(usuarioId: string, filialId: string | null): void {
  try {
    const key = `relaxabarber:filial:${usuarioId}`;
    if (filialId) localStorage.setItem(key, filialId); else localStorage.removeItem(key);
  } catch { /* Preferência é opcional; autorização nunca depende dela. */ }
}
export function recursoPorFilial(url: string | undefined): boolean {
  return /^\/(agendamentos|comandas|clientes)(\/|$|\?)/.test(url ?? '') || /^\/usuarios\/barbeiros(\?|$)/.test(url ?? '');
}
