import axios from 'axios';

// Instância exclusiva: nunca injeta token da equipe ou filial ativa.
export const apiPortal = axios.create({ baseURL: import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : ''), withCredentials: true, timeout: 15000 });
export interface PerfilCliente { id: string; nome: string; email: string; telefone: string }
export interface PedidoCodigo { solicitacao_id: string; mensagem: string }
export const cadastrarConta = async (dados: { nome: string; telefone: string; email: string; senha: string }) =>
  (await apiPortal.post<PedidoCodigo>('/portal-clientes/cadastro', dados)).data;
export const recuperarConta = async (email: string) => (await apiPortal.post<PedidoCodigo>('/portal-clientes/recuperar', { email })).data;
export const confirmarConta = async (solicitacao_id: string, codigo: string) =>
  (await apiPortal.post<{ mensagem: string }>('/portal-clientes/ativar', { solicitacao_id, codigo })).data;
export const redefinirSenhaCliente = async (solicitacao_id: string, codigo: string, senha: string) =>
  (await apiPortal.post<{ mensagem: string }>('/portal-clientes/redefinir', { solicitacao_id, codigo, senha })).data;
export const entrarCliente = async (email: string, senha: string) => { await apiPortal.post('/portal-clientes/login', { email, senha }); };
export const perfilCliente = async (signal?: AbortSignal) => (await apiPortal.get<PerfilCliente>('/portal-clientes/me', { signal })).data;
export const sairCliente = async () => { await apiPortal.post('/portal-clientes/logout'); };
export const solicitarTrocaEmail = async (email_novo: string) =>
  (await apiPortal.post<PedidoCodigo>('/portal-clientes/troca-email', { email_novo })).data;
export const confirmarTrocaEmail = async (etapa: 'atual' | 'novo', solicitacao_id: string, codigo: string) =>
  (await apiPortal.post<{ mensagem: string }>(`/portal-clientes/troca-email/confirmar-${etapa}`, { solicitacao_id, codigo })).data;
