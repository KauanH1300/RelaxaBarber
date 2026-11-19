import axios from 'axios';
import type { Servico } from './servico';
import { apiPortal } from './portalCliente';

// Public catalog never receives employee credentials or branch context.
export const apiPublica = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000', timeout: 15000, withCredentials: false });
export async function catalogoPublico(signal?: AbortSignal): Promise<Servico[]> {
  const { data } = await apiPublica.get<Servico[]>('/servicos/', { signal });
  return data.filter(s => s.ativo && typeof s.id === 'string' && typeof s.nome === 'string' && Number.isFinite(Number(s.preco)) && Number(s.preco) >= 0 && s.tempo_estimado > 0);
}

export interface ProfissionalPublico { id: string; nome: string }
export interface HorariosPublicos { data: string; duracao: number; fuso: string; horarios: string[] }
export interface ReservaConfirmada { id: string; status: string; data: string; hora_inicio: string; hora_fim: string; barbeiro: ProfissionalPublico; servico: string; fuso: string }
export interface FilialPublica { id: string; nome: string; endereco: string }
export const filiaisPublicas = async (signal?: AbortSignal) => (await apiPublica.get<FilialPublica[]>('/publico/filiais', { signal })).data;
export const servicosDaFilial = async (filial: string, signal?: AbortSignal) => (await apiPublica.get<Servico[]>(`/publico/filiais/${encodeURIComponent(filial)}/servicos`, { signal })).data;
function parametros(filial: string, servicos: string[]) { const p = new URLSearchParams({ filial_id: filial }); servicos.forEach(s => p.append('servico_id', s)); return p; }
export const barbeirosPublicos = async (filial: string, servicos: string[], signal?: AbortSignal) => (await apiPublica.get<ProfissionalPublico[]>('/publico/barbeiros', { params: parametros(filial, servicos), signal })).data;
export const horariosPublicos = async (filial: string, servicos: string[], data: string, barbeiro: string, signal?: AbortSignal) => { const p = parametros(filial, servicos); p.set('data', data); if (barbeiro !== 'qualquer') p.set('barbeiro_id', barbeiro); return (await apiPublica.get<HorariosPublicos>('/publico/horarios', { params: p, signal })).data; };
export const confirmarReserva = async (e: EscolhasAgendamento) => (await apiPortal.post<ReservaConfirmada>('/portal-clientes/reservas', { filial_id: e.filial, servicos_ids: e.servicos, barbeiro_id: e.barbeiro === 'qualquer' ? null : e.barbeiro, data: e.data, hora_inicio: e.hora, chave: e.chave })).data;
export const consultarReserva = async (chave: string) => (await apiPortal.get<ReservaConfirmada>(`/portal-clientes/reservas/${chave}`)).data;
export interface EscolhasAgendamento { filial: string; servicos: string[]; barbeiro: string; data: string; hora: string; chave?: string }
export const escolhasVazias: EscolhasAgendamento = { filial: '', servicos: [], barbeiro: '', data: '', hora: '' };
const chave = 'rb_agendamento_publico_v1';
export function hojeLocal() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Recife', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  return ['year', 'month', 'day'].map(t => parts.find(p => p.type === t)!.value).join('-');
}
export function escolhasValidas(value: unknown): value is EscolhasAgendamento {
  if (!value || typeof value !== 'object') return false;
  const v = value as EscolhasAgendamento;
  return typeof v.filial === 'string' && (v.filial === '' || /^[0-9a-f-]{36}$/i.test(v.filial))
    && Array.isArray(v.servicos) && v.servicos.length <= 20 && v.servicos.every(s => typeof s === 'string' && /^[0-9a-f-]{36}$/i.test(s)) && new Set(v.servicos).size === v.servicos.length
    && (v.barbeiro === '' || v.barbeiro === 'qualquer' || (typeof v.barbeiro === 'string' && /^[0-9a-f-]{36}$/i.test(v.barbeiro)))
    && (v.chave === undefined || /^[0-9a-f-]{36}$/i.test(v.chave))
    && typeof v.data === 'string' && (v.data === '' || /^\d{4}-\d{2}-\d{2}$/.test(v.data))
    && typeof v.hora === 'string' && (v.hora === '' || /^([01]\d|2[0-3]):[0-5]\d$/.test(v.hora));
}
export function lerEscolhas(): EscolhasAgendamento {
  try {
    const saved = JSON.parse(sessionStorage.getItem(chave) || 'null');
    if (saved && typeof saved.expira === 'number' && saved.expira > Date.now() && saved.expira <= Date.now() + 2 * 3600_000 && escolhasValidas(saved.escolhas)) return saved.escolhas;
  } catch { /* Storage blocked or invalid: start with an empty draft. */ }
  return { ...escolhasVazias };
}
export function guardarEscolhas(escolhas: EscolhasAgendamento): boolean {
  try {
    if (!escolhasValidas(escolhas)) return false;
    sessionStorage.setItem(chave, JSON.stringify({ expira: Date.now() + 2 * 3600_000, escolhas }));
    return true;
  } catch { return false; }
}
export function retornoAgendamento(search: string) { return new URLSearchParams(search).get('retorno') === 'agendamento'; }
export function destinoAposLogin(search: string) { return retornoAgendamento(search) ? '/agendar?etapa=confirmacao' : new URLSearchParams(search).get('retorno') === 'meus-agendamentos' ? '/cliente/agendamentos' : '/cliente'; }
export function sufixoRetorno(search: string) { return retornoAgendamento(search) ? '?retorno=agendamento' : new URLSearchParams(search).get('retorno') === 'meus-agendamentos' ? '?retorno=meus-agendamentos' : ''; }
