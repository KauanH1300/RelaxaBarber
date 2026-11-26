export const EVENTO_SESSAO = 'relaxabarber:sessao';
for (const nome of ['localStorage', 'sessionStorage'] as const) {
  try { window[nome].removeItem('token'); } catch { /* Storage may be disabled. */ }
}
// Only a local generation marker, never an authentication credential.
let geracao: string | null = crypto.randomUUID();
export function obterToken(): string | null { return geracao; }
export function iniciarSessao(): void { geracao = crypto.randomUUID(); window.dispatchEvent(new Event(EVENTO_SESSAO)); }
export function encerrarSessao(): void { geracao = null; window.dispatchEvent(new Event(EVENTO_SESSAO)); }
export function invalidarSessao(status: number | undefined, url: string | undefined, marca: unknown): void {
  if (status === 401 && url !== '/auth/login' && geracao && marca === geracao) encerrarSessao();
}
