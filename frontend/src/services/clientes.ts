import axios from 'axios';
import api from './api';
import { mensagemErro } from './erros';
import type { UsuarioLogado } from './usuario';

export interface Cliente {
  id: string;
  nome: string;
  telefone: string;
  email: string | null;
  ativo: boolean;
  conta_ativada: boolean;
  data_cadastro: string;
}

export interface DadosCliente { nome: string; telefone: string; email: string }

export function podeGerenciarClientes(usuario: Pick<UsuarioLogado, 'perfil' | 'ativo'>): boolean {
  return usuario.ativo && ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'].includes(usuario.perfil);
}
export async function listarClientes(busca: string, signal?: AbortSignal): Promise<Cliente[]> {
  return (await api.get<Cliente[]>('/clientes', { params: { busca: busca.trim() || undefined }, signal })).data;
}
export function erroCliente(erro: unknown, fallback: string): string {
  if (axios.isAxiosError(erro) && erro.response?.status === 409) {
    return 'Já existe um cadastro com este telefone ou e-mail. Confira os dados. Se ele não aparece nesta unidade, procure o administrador. Este formulário não associa cadastros de outras filiais.';
  }
  return mensagemErro(erro, fallback);
}

export function prepararCliente(dados: DadosCliente) {
  const nome = dados.nome.trim();
  const telefone = dados.telefone.trim();
  const email = dados.email.trim();
  if (!nome || nome.length > 150) throw new Error('Informe um nome com até 150 caracteres.');
  if (!telefone || telefone.length > 20) throw new Error('Informe um telefone com até 20 caracteres.');
  // Validação inicial; EmailStr e a unicidade continuam sob autoridade da API.
  if (email && (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(email))) {
    throw new Error('Informe um e-mail válido ou deixe o campo vazio.');
  }
  return { nome, telefone, email: email || null };
}

export interface RascunhoCliente { dados: DadosCliente; base: DadosCliente; incerto: boolean; expira: number }
export const dadosClienteVazios = (): DadosCliente => ({ nome: '', telefone: '', email: '' });
export const clienteParaDados = (c: Cliente): DadosCliente => ({ nome: c.nome, telefone: c.telefone, email: c.email ?? '' });
export const dadosClienteAlterados = (a: DadosCliente, b: DadosCliente): boolean => a.nome !== b.nome || a.telefone !== b.telefone || a.email !== b.email;
export const chaveRascunhoCliente = (usuario: string, filial: string, id?: string): string => `relaxabarber:cliente:${usuario}:${filial}:${id ?? 'novo'}`;
export function serializarRascunhoCliente(dados: DadosCliente, base: DadosCliente, incerto = false, agora = Date.now()): string {
  return JSON.stringify({ dados, base, incerto, expira: agora + 8 * 60 * 60 * 1000 });
}
export function lerRascunhoCliente(raw: string | null, agora = Date.now()): RascunhoCliente | null {
  try {
    const r = JSON.parse(raw ?? 'null');
    const valido = (v: unknown): v is DadosCliente => !!v && typeof v === 'object' && ['nome', 'telefone', 'email'].every((k) => {
      const value = (v as Record<string, unknown>)[k];
      return typeof value === 'string' && value.length <= 4000;
    });
    return r && typeof r.expira === 'number' && r.expira > agora && typeof r.incerto === 'boolean' && valido(r.dados) && valido(r.base) ? r : null;
  } catch { return null; }
}

export async function consultarCliente(id: string, filialId: string, signal?: AbortSignal): Promise<Cliente> {
  return (await api.get<Cliente>(`/clientes/${encodeURIComponent(id)}`, { params: { filial_id: filialId }, signal })).data;
}

export async function salvarCliente(dados: DadosCliente, filialId: string, id?: string): Promise<Cliente> {
  const payload = prepararCliente(dados);
  return id
    ? (await api.patch<Cliente>(`/clientes/${encodeURIComponent(id)}`, payload, { params: { filial_id: filialId } })).data
    : (await api.post<Cliente>('/clientes', { ...payload, filial_id: filialId })).data;
}
