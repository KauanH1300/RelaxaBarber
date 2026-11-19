import api from './api';

export type Operacao = { chave: string; metodo: 'post' | 'put' | 'delete'; caminho: string; dados?: unknown };

export function lerPendente(storage: string): Operacao | null {
  const raw = localStorage.getItem(storage);
  if (!raw) return null;
  const p = JSON.parse(raw) as Operacao;
  if (!p || !/^[0-9a-f-]{36}$/i.test(p.chave) || !['post', 'put', 'delete'].includes(p.metodo) || !/^\/comandas\/(avulsas|[0-9a-f-]{36}\/produtos(?:\/[0-9a-f-]{36})?)$/i.test(p.caminho)) throw new Error('Operação pendente inválida. Preserve os dados e procure o administrador.');
  return p;
}

export async function enviar(storage: string, filial: string, operacao: Operacao) {
  const anterior = lerPendente(storage);
  if (anterior && JSON.stringify(anterior) !== JSON.stringify(operacao)) throw new Error('Recupere a operação pendente antes de iniciar outra.');
  localStorage.setItem(storage, JSON.stringify(operacao));
  try {
    const resposta = await api.request({ method: operacao.metodo, url: operacao.caminho, data: operacao.dados, params: { filial_id: filial }, headers: { 'Idempotency-Key': operacao.chave } });
    if (operacao.caminho === '/comandas/avulsas' && !resposta.data?.id) throw new Error('Resposta de abertura inválida; preserve a chave e recupere a operação.');
    if (JSON.stringify(lerPendente(storage)) === JSON.stringify(operacao)) localStorage.removeItem(storage);
    return resposta.data as { id?: string };
  } catch (erro) {
    const status = (erro as { response?: { status?: number } })?.response?.status;
    const codigo = (erro as { response?: { data?: { detail?: { codigo?: string } } } })?.response?.data?.detail?.codigo;
    if (status && status >= 400 && status < 500 && status !== 408 && status !== 429 && codigo !== 'conflito_idempotencia' && JSON.stringify(lerPendente(storage)) === JSON.stringify(operacao)) localStorage.removeItem(storage);
    throw erro;
  }
}
