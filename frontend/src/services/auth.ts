import api from './api';
import type { UsuarioLogado } from './usuario';
import { encerrarSessao, obterToken, iniciarSessao } from './sessao';

type PrazosLogin = { validade_segundos: number; reenvio_segundos: number };
type ResultadoLogin = { mensagem: string } | ({ verificacao_email: true } & PrazosLogin);
export type DispositivoConfiavel = { id: string; criado_em: string; expira_em: string; atual: boolean };

function registrarLogin() {
  try { localStorage.removeItem('equipe:confirmacao-adiada'); } catch { /* Armazenamento indisponível. */ }
  iniciarSessao();
}

export async function login(email: string, senha: string) {
  const dados = new URLSearchParams();
  dados.append('username', email);
  dados.append('password', senha);

  const { data } = await api.post<ResultadoLogin>('/auth/login', dados, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });

  if (!('verificacao_email' in data)) registrarLogin();
  return data;
}

export async function reenviarLoginAdmin() {
  return (await api.post<PrazosLogin>('/auth/login/email/reenviar')).data;
}

export async function verificarLoginAdmin(codigo: string, confiar: boolean) {
  await api.post('/auth/login/email/verificar', { codigo, confiar });
  registrarLogin();
}

export async function consultarDispositivos() {
  return (await api.get<DispositivoConfiavel[]>('/auth/dispositivos-confiaveis')).data;
}

export async function revogarDispositivos(id?: string) {
  await api.delete(id ? `/auth/dispositivos-confiaveis/${id}` : '/auth/dispositivos-confiaveis');
}

export async function getMe() {
  const { data } = await api.get<UsuarioLogado>('/auth/me');
  return data;
}

export async function logout() {
  const token = obterToken();
  if (!token) return;
  try {
    await api.post('/auth/logout');
  } catch (erro) {
    // Um 401 referente ao token ativo já é tratado pelo interceptor.
    if (obterToken() === token) throw erro;
    return;
  }
  if (obterToken() === token) encerrarSessao();
}

export async function solicitarCodigoEquipe(email: string) {
  return (await api.post<{ solicitacao_id: string; mensagem: string }>('/auth/recuperar', { email })).data;
}

export async function redefinirSenhaEquipe(solicitacao_id: string, codigo: string, senha: string) {
  await api.post('/auth/redefinir', { solicitacao_id, codigo, senha });
}
export async function enviarConfirmacaoEmail() {
  return (await api.post<{ solicitacao_id: string; validade_segundos: number; reenvio_segundos: number }>(
    '/auth/confirmacao-email',
  )).data;
}

export async function confirmarEmail(solicitacao_id: string, codigo: string) {
  return (await api.post<UsuarioLogado>('/auth/confirmacao-email/confirmar', { solicitacao_id, codigo })).data;
}

export async function trocarSenhaEquipe(senha_atual: string, senha: string) {
  await api.post('/auth/trocar-senha', { senha_atual, senha });
  encerrarSessao();
}
