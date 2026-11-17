import api from './api';
import type { Comanda, ItemComanda } from './comandas';
import type { UsuarioLogado } from './usuario';
import { permiteInclusao } from './itensComanda';

export interface Ajuste { acao: 'quantidade' | 'substituir' | 'remover'; versao: number; motivo: string; quantidade?: number; servico_id?: string }
export interface PreviaAjuste {
  comanda_id: string; item_id: string; versao: number; anterior: ItemComanda; posterior: ItemComanda;
  total_anterior: string; total: string; recebido_liquido: string; saldo: string; exige_fechamento: boolean; conferencia: string;
}
export interface ResultadoAjuste extends PreviaAjuste { acao: Ajuste['acao']; motivo: string; registrado_por: string; registrado_em: string; chave_idempotencia: string; fechado: boolean }
export interface AjustePendente { itemId: string; chave: string; payload: Ajuste & { conferencia: string; confirmar_fechamento: boolean } }
export function podeAjustar(usuario: UsuarioLogado, comanda: Comanda): boolean {
  return ['admin', 'recepcao'].includes(usuario.perfil) && permiteInclusao(usuario, comanda);
}
export function chaveAjuste(usuario: string, comanda: Comanda): string { return `relaxabarber:ajustes:v1:${usuario}:${comanda.filial_id}:${comanda.id}`; }
function validar(p: AjustePendente): void {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!p || Object.keys(p).sort().join() !== 'chave,itemId,payload' || !uuid.test(p.itemId) || !uuid.test(p.chave) || !p.payload
    || Object.keys(p.payload).some(k => !['acao','versao','motivo','quantidade','servico_id','conferencia','confirmar_fechamento'].includes(k))
    || typeof p.payload.conferencia !== 'string' || !/^[0-9a-f]{64}$/.test(p.payload.conferencia)
    || !Number.isInteger(p.payload.versao) || p.payload.versao < 0 || typeof p.payload.motivo !== 'string' || !p.payload.motivo.trim()
    || p.payload.motivo.length > 1000
    || typeof p.payload.confirmar_fechamento !== 'boolean' || !['quantidade', 'substituir', 'remover'].includes(p.payload.acao)) throw new Error('Ajuste pendente inválido. Preserve o registro e procure o administrador.');
  const { acao, quantidade, servico_id } = p.payload;
  if ((acao !== 'remover' && (!Number.isInteger(quantidade) || quantidade! < 1 || quantidade! > 999))
    || (acao === 'substituir' && !uuid.test(servico_id ?? ''))
    || (acao === 'quantidade' && servico_id !== undefined)
    || (acao === 'remover' && (quantidade !== undefined || servico_id !== undefined))) throw new Error('Conteúdo do ajuste pendente inválido. Preserve o registro.');
}
export function lerAjuste(storage: string): AjustePendente | null {
  const raw = sessionStorage.getItem(storage); if (!raw) return null;
  const p = JSON.parse(raw) as AjustePendente; validar(p); return p;
}
export function salvarAjuste(storage: string, p: AjustePendente): void {
  validar(p); const anterior = lerAjuste(storage);
  if (anterior && JSON.stringify(anterior) !== JSON.stringify(p)) throw new Error('Recupere o ajuste original antes de iniciar outro.');
  sessionStorage.setItem(storage, JSON.stringify(p));
}
export function limparAjuste(storage: string, p: AjustePendente): void {
  if (JSON.stringify(lerAjuste(storage)) === JSON.stringify(p)) sessionStorage.removeItem(storage);
}
export async function previaAjuste(c: Comanda, itemId: string, payload: Ajuste): Promise<PreviaAjuste> {
  return (await api.post<PreviaAjuste>(`/comandas/${c.id}/itens/${itemId}/previa`, payload, { params: { filial_id: c.filial_id } })).data;
}
export async function aplicarAjuste(c: Comanda, p: AjustePendente): Promise<ResultadoAjuste> {
  validar(p);
  return (await api.post<ResultadoAjuste>(`/comandas/${c.id}/itens/${p.itemId}/alteracoes`, p.payload, { params: { filial_id: c.filial_id }, headers: { 'Idempotency-Key': p.chave } })).data;
}
export async function historicoAjustes(c: Comanda, signal: AbortSignal): Promise<ResultadoAjuste[]> {
  return (await api.get<ResultadoAjuste[]>(`/comandas/${c.id}/itens/alteracoes`, { params: { filial_id: c.filial_id }, signal })).data;
}
