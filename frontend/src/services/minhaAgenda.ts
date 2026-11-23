import { apiPortal } from './portalCliente';
export interface MeuAgendamento {
  id: string; filial: string; servicos: { nome: string; duracao: number; valor: string | null }[];
  barbeiro: { id: string; nome: string }; data: string; hora_inicio: string; hora_fim: string;
  duracao: number; valor: string | null; status: string; atualizado_em: string | null;
  proximo: boolean; pode_cancelar: boolean; pode_remarcar: boolean; fuso: string;
}
export interface OpcoesRemarcacao { barbeiros: { id: string; nome: string }[]; horarios: string[]; fuso: string }
const url = '/portal-clientes/agendamentos';
export const meusAgendamentos = async (signal?: AbortSignal) => (await apiPortal.get<MeuAgendamento[]>(url, { signal })).data;
export const meuAgendamento = async (id: string) => (await apiPortal.get<MeuAgendamento>(`${url}/${encodeURIComponent(id)}`)).data;
export const opcoesRemarcacao = async (id: string, data: string, barbeiro: string, signal?: AbortSignal) => (await apiPortal.get<OpcoesRemarcacao>(`${url}/${encodeURIComponent(id)}/opcoes`, { params: { ...(data ? { data } : {}), ...(barbeiro && barbeiro !== 'qualquer' ? { barbeiro_id: barbeiro } : {}) }, signal })).data;
export const cancelarMeuAgendamento = async (a: MeuAgendamento) => (await apiPortal.post<MeuAgendamento>(`${url}/${encodeURIComponent(a.id)}/cancelamento`, { atualizado_em_esperado: a.atualizado_em })).data;
export const remarcarMeuAgendamento = async (a: MeuAgendamento, data: string, hora: string, barbeiro: string) => (await apiPortal.patch<MeuAgendamento>(`${url}/${encodeURIComponent(a.id)}/reagendamento`, { atualizado_em_esperado: a.atualizado_em, data, hora_inicio: hora, barbeiro_id: barbeiro === 'qualquer' ? null : barbeiro })).data;
