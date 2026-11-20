import axios from 'axios';
import type { AxiosResponse } from 'axios';

export const versaoDesatualizada = (erro: unknown) => axios.isAxiosError(erro) &&
  erro.response?.status === 409 && erro.response?.data?.detail?.codigo === 'versao_desatualizada';

export function lerVersao(headers: AxiosResponse['headers']): string {
  if (typeof headers.etag !== 'string' || !/^"[0-9a-f]{64}"$/.test(headers.etag)) {
    throw new Error('Não foi possível verificar a versão dos dados.');
  }
  return headers.etag;
}
