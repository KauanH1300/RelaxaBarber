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
export async function cadastrarFuncionario(dados: DadosFuncionario, senha: string, filialIds: string[]): Promise<Funcionario> {
  const { nome, email, telefone, perfil } = dados;
  return (await api.post('/usuarios', { nome, email, telefone, perfil, senha, filial_ids: filialIds })).data;
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
