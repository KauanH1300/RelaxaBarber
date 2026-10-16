export const EVENTO_SESSAO = 'relaxabarber:sessao';

export function obterToken(): string | null {
  return localStorage.getItem('token');
}

export function encerrarSessao(): void {
  localStorage.removeItem('token');
  window.dispatchEvent(new Event(EVENTO_SESSAO));
}

export function invalidarSessao(status: number | undefined, url: string | undefined, autorizacao: unknown): void {
  const token = obterToken();
  // Uma resposta antiga não pode encerrar uma sessão iniciada depois dela.
  if (status === 401 && url !== '/auth/login' && token && autorizacao === `Bearer ${token}`) {
    encerrarSessao();
  }
}
