import api from './api';
import type { Comanda } from './comandas';
import type { UsuarioLogado } from './usuario';

export interface CancelamentoComanda {
  comanda_id: string; filial_id: string; registrado_por: string; registrado_em: string;
  motivo: string; chave_idempotencia: string; versao: number;
  status: 'cancelada'; status_anterior: 'pendente' | 'aberta';
}
export interface CancelamentoPendente {
  chave: string; payload: { versao: number; motivo: string; confirmado: true };
}
export function podeCancelarComanda(usuario: Pick<UsuarioLogado, 'perfil'>, comanda: Comanda): boolean {
  return ['admin', 'recepcao'].includes(usuario.perfil) && ['pendente', 'aberta'].includes(comanda.status)
    && !comanda.data_fechamento && !comanda.itens.some(i => i.ativo !== false);
}
export function chaveCancelamento(usuario: string, comanda: Comanda): string {
  return `relaxabarber:cancelamento:v1:${usuario}:${comanda.filial_id}:${comanda.id}`;
}
export function lerCancelamento(chave: string): CancelamentoPendente | null {
  const raw = localStorage.getItem(chave);
  if (!raw) return null;
  const p: CancelamentoPendente = JSON.parse(raw);
  if (!p || !/^[0-9a-f-]{36}$/i.test(p.chave) || !p.payload || p.payload.confirmado !== true
    || !Number.isInteger(p.payload.versao) || p.payload.versao < 0 || typeof p.payload.motivo !== 'string'
    || !p.payload.motivo.trim() || p.payload.motivo.length > 1000) throw Error('Cancelamento pendente inválido');
  return p;
}
export function salvarCancelamento(chave: string, pendente: CancelamentoPendente): void {
  const anterior = lerCancelamento(chave);
  if (anterior && JSON.stringify(anterior) !== JSON.stringify(pendente)) throw Error('Recupere o cancelamento original');
  localStorage.setItem(chave, JSON.stringify(pendente));
}
export async function cancelarComanda(comanda: Comanda, pendente: CancelamentoPendente): Promise<CancelamentoComanda> {
  return (await api.post<CancelamentoComanda>(`/comandas/${encodeURIComponent(comanda.id)}/cancelamento`, pendente.payload,
    { params: { filial_id: comanda.filial_id }, headers: { 'Idempotency-Key': pendente.chave } })).data;
}
