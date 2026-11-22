import axios from 'axios';
import api from './api';
import { mensagemErro } from './erros';
import { diaLocal } from '../pages/gerencial/formatacao';
import type { UsuarioLogado } from './usuario';

export interface Cliente {
  id: string;
  nome: string;
  telefone: string;
  email: string | null;
  ativo: boolean;
  conta_ativada: boolean;
  data_cadastro: string;
  data_nascimento?: string | null;
  preferencias?: string | null;
  possivel_duplicidade?: boolean;
}

type DadosRascunho = { nome: string; telefone: string; email: string };
export interface DadosCliente extends DadosRascunho { data_nascimento: string; preferencias: string }
export const LIMITE_PREFERENCIAS = 2000;

export function podeGerenciarClientes(usuario: Pick<UsuarioLogado, 'perfil' | 'ativo'>): boolean {
  return usuario.ativo && ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro'].includes(usuario.perfil);
}
export async function listarClientes(busca: string, signal?: AbortSignal): Promise<Cliente[]> {
  return (await api.get<Cliente[]>('/clientes', { params: { busca: busca.trim() || undefined }, signal })).data;
}
export function erroCliente(erro: unknown, fallback: string): string {
  if (axios.isAxiosError(erro) && erro.response?.status === 409) {
    return 'Já existe um cadastro com este e-mail ou a alteração não é permitida. Confira os dados ou procure o administrador.';
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
  const nascimento = dados.data_nascimento ?? '';
  const preferencias = (dados.preferencias ?? '').trim();
  if (nascimento) {
    const data = new Date(nascimento + 'T00:00:00Z');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(nascimento) || nascimento.startsWith('0000') ||
        Number.isNaN(data.valueOf()) || data.toISOString().slice(0, 10) !== nascimento || nascimento > diaLocal()) {
      throw new Error('Informe uma data de nascimento válida que não esteja no futuro.');
    }
  }
  if ([...preferencias].length > LIMITE_PREFERENCIAS) throw new Error('Informe até 2.000 caracteres para as preferências.');
  return { nome, telefone, email: email || null, data_nascimento: nascimento || null, preferencias: preferencias || null };
}

export interface RascunhoCliente { dados: DadosRascunho; base: DadosRascunho; incerto: boolean; expira: number; chaveCadastro?: string }
export const dadosClienteVazios = (): DadosCliente => ({ nome: '', telefone: '', email: '', data_nascimento: '', preferencias: '' });
export const clienteParaDados = (c: Cliente): DadosCliente => ({
  nome: c.nome, telefone: c.telefone, email: c.email ?? '',
  data_nascimento: c.data_nascimento ?? '', preferencias: c.preferencias ?? '',
});
export const dadosRascunhoAlterados = (a: DadosRascunho, b: DadosRascunho) =>
  a.nome !== b.nome || a.telefone !== b.telefone || a.email !== b.email;
export const dadosClienteAlterados = (a: DadosCliente, b: DadosCliente) =>
  dadosRascunhoAlterados(a, b) || a.data_nascimento !== b.data_nascimento || a.preferencias !== b.preferencias;
const dadosRascunho = ({ nome, telefone, email }: DadosRascunho): DadosRascunho => ({ nome, telefone, email });
export const chaveRascunhoCliente = (usuario: string, filial: string, id?: string): string => `relaxabarber:cliente:${usuario}:${filial}:${id ?? 'novo'}`;
export function serializarRascunhoCliente(dados: DadosCliente, base: DadosCliente, incerto = false, agora = Date.now(), chaveCadastro?: string): string {
  return JSON.stringify({ dados: dadosRascunho(dados), base: dadosRascunho(base), incerto, expira: agora + 8 * 60 * 60 * 1000, chaveCadastro });
}
export function lerRascunhoCliente(raw: string | null, agora = Date.now()): RascunhoCliente | null {
  try {
    const r = JSON.parse(raw ?? 'null');
    const valido = (v: unknown): v is DadosRascunho => !!v && typeof v === 'object' && ['nome', 'telefone', 'email'].every((k) => {
      const value = (v as Record<string, unknown>)[k];
      return typeof value === 'string' && value.length <= 4000;
    });
    return r && typeof r.expira === 'number' && r.expira > agora && typeof r.incerto === 'boolean' && valido(r.dados) && valido(r.base)
      ? { dados: dadosRascunho(r.dados), base: dadosRascunho(r.base), expira: r.expira, incerto: r.incerto,
        ...(r.incerto && typeof r.chaveCadastro === 'string' && /^[0-9a-f-]{36}$/i.test(r.chaveCadastro)
          ? { chaveCadastro: r.chaveCadastro } : {}) } : null;
  } catch { return null; }
}

export async function consultarCliente(id: string, filialId: string, signal?: AbortSignal): Promise<Cliente> {
  return (await api.get<Cliente>(`/clientes/${encodeURIComponent(id)}`, { params: { filial_id: filialId }, signal })).data;
}

export async function conferirCadastroCliente(chave: string, filialId: string): Promise<Cliente> {
  return (await api.get<Cliente>(`/clientes/cadastros/${encodeURIComponent(chave)}`, { params: { filial_id: filialId } })).data;
}

export async function salvarCliente(dados: DadosCliente, filialId: string, id?: string, chave?: string): Promise<Cliente> {
  const payload = prepararCliente(dados);
  return id
    ? (await api.patch<Cliente>(`/clientes/${encodeURIComponent(id)}`, payload, { params: { filial_id: filialId } })).data
    : (await api.post<Cliente>('/clientes', { ...payload, filial_id: filialId },
      chave ? { headers: { 'Idempotency-Key': chave } } : undefined)).data;
}
