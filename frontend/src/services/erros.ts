import axios from 'axios';

function lerDetalhe(detail: unknown): string | undefined {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const mensagens = detail.flatMap((item: unknown) => {
      if (typeof item === 'string') return [item];
      if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') return [item.msg];
      return [];
    });
    if (mensagens.length) return mensagens.join('; ');
  }
}

export function mensagemErro(erro: unknown, fallback: string): string {
  if (!axios.isAxiosError(erro)) return fallback;
  if (erro.response?.status === 401 && erro.config?.url !== '/auth/login') return 'Sessão expirada. Entre novamente.';
  const detalhe = lerDetalhe(erro.response?.data?.detail);
  if (detalhe) return detalhe;
  if (erro.response?.status === 403) return 'Sem permissão para esta operação.';
  if (!erro.response) return `${fallback}. Verifique sua conexão.`;
  return fallback;
}

export function escritaIncerta(erro: unknown): boolean {
  return axios.isAxiosError(erro) && (!erro.response || [500, 502, 503, 504].includes(erro.response.status));
}

export function deveConferirRegistros(erro: unknown): boolean {
  return axios.isAxiosError(erro) && (erro.response?.status === 409 || escritaIncerta(erro));
}
