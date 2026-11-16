import axios from 'axios';
import type { Servico } from './servico';

// Public catalog never receives employee credentials or branch context.
export const apiPublica = axios.create({ baseURL: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000', timeout: 15000, withCredentials: false });
export async function catalogoPublico(signal?: AbortSignal): Promise<Servico[]> {
  const { data } = await apiPublica.get<Servico[]>('/servicos/', { signal });
  return data.filter(s => s.ativo && typeof s.id === 'string' && typeof s.nome === 'string' && Number.isFinite(Number(s.preco)) && Number(s.preco) >= 0 && s.tempo_estimado > 0);
}

export const preferencias = ['Sem preferência', 'Rodrigo Relaxa', 'Higor Rodrigo'] as const;
export interface EscolhasAgendamento { servico: string; barbeiro: string; data: string; hora: string }
export const escolhasVazias: EscolhasAgendamento = { servico: '', barbeiro: '', data: '', hora: '' };
const chave = 'rb_agendamento_publico_v1';
export function hojeLocal() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}
export function escolhasValidas(value: unknown): value is EscolhasAgendamento {
  if (!value || typeof value !== 'object') return false;
  const v = value as EscolhasAgendamento;
  return typeof v.servico === 'string' && v.servico.length <= 100
    && (v.barbeiro === '' || preferencias.some(p => p === v.barbeiro))
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
    sessionStorage.setItem(chave, JSON.stringify({ expira: Date.now() + 2 * 3600_000, escolhas: { servico: escolhas.servico, barbeiro: escolhas.barbeiro, data: escolhas.data, hora: escolhas.hora } }));
    return true;
  } catch { return false; }
}
export function retornoAgendamento(search: string) { return new URLSearchParams(search).get('retorno') === 'agendamento'; }
export function destinoAposLogin(search: string) { return retornoAgendamento(search) ? '/agendar?etapa=confirmacao' : '/cliente'; }
export function sufixoRetorno(search: string) { return retornoAgendamento(search) ? '?retorno=agendamento' : ''; }
