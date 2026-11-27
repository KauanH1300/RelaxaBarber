import api from './api';
import type { UsuarioLogado } from './usuario';
import type { PerfilAgenda } from './permissoesAgenda';

export type Funcionario = UsuarioLogado;
export interface DadosFuncionario { nome: string; email: string; telefone: string | null; perfil: PerfilAgenda; ativo: boolean }
export interface VinculoFuncionario { id: string; usuario_id: string; filial_id: string; ativo: boolean }
export const podeGerenciarFuncionarios = (usuario: Pick<UsuarioLogado, 'perfil'>) => usuario.perfil === 'admin';
export async function listarFuncionarios(signal?: AbortSignal): Promise<Funcionario[]> {
  return (await api.get('/usuarios', { signal })).data;
}
export async function cadastrarFuncionario(dados: DadosFuncionario, senha: string, filialIds: string[], chave?: string): Promise<Funcionario> {
  const { nome, email, telefone, perfil } = dados;
  return (await api.post('/usuarios', { nome, email, telefone, perfil, senha, filial_ids: filialIds },
    chave ? { headers: { 'Idempotency-Key': chave } } : undefined)).data;
}
export async function conferirCadastroFuncionario(chave: string): Promise<Funcionario> {
  return (await api.get(`/usuarios/cadastros/${encodeURIComponent(chave)}`)).data;
}
export async function atualizarFuncionario(id: string, dados: DadosFuncionario): Promise<Funcionario> {
  return (await api.patch(`/usuarios/${encodeURIComponent(id)}`, dados)).data;
}
export async function listarVinculos(filialId: string, signal?: AbortSignal): Promise<VinculoFuncionario[]> {
  return (await api.get(`/filiais/${encodeURIComponent(filialId)}/usuarios`, { signal })).data;
}
export async function definirVinculo(filialId: string, usuarioId: string, ativo: boolean): Promise<VinculoFuncionario> {
  return (await api.put(`/filiais/${encodeURIComponent(filialId)}/usuarios/${encodeURIComponent(usuarioId)}`, { ativo })).data;
}

export interface RestricoesServicos { servicos: { id: string; nome: string; ativo: boolean }[]; restricoes: string[] }
const urlRestricoes = (filialId: string, barbeiroId: string) => `/filiais/${encodeURIComponent(filialId)}/barbeiros/${encodeURIComponent(barbeiroId)}/restricoes-servicos`;
export async function consultarRestricoesServicos(filialId: string, barbeiroId: string, signal?: AbortSignal): Promise<RestricoesServicos> {
  return (await api.get<RestricoesServicos>(urlRestricoes(filialId, barbeiroId), { signal })).data;
}
export async function salvarRestricoesServicos(filialId: string, barbeiroId: string, servicos: string[]): Promise<{ restricoes: string[] }> {
  return (await api.put(urlRestricoes(filialId, barbeiroId), { servicos })).data;
}

export async function recuperarFuncionario(id: string, senhaAtual: string, senha: string, motivo: string) {
  await api.post(`/usuarios/${encodeURIComponent(id)}/recuperacao-administrativa`, {
    senha_atual_admin: senhaAtual, senha, motivo,
  });
}
