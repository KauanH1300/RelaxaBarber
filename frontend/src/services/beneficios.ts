import api from './api';
import type { Comanda, ItemComanda } from './comandas';
import type { UsuarioLogado } from './usuario';
import { podeAjustar } from './alteracoesItens';

export type TipoDesconto = 'nenhum' | 'valor' | 'percentual' | 'cortesia';
export interface Beneficio { acao: 'item' | 'comanda' | 'encerramento_gratuito'; versao: number; motivo: string; item_id?: string; desconto_tipo?: TipoDesconto; desconto_valor?: string }
export interface EstadoBeneficios { itens: ItemComanda[]; desconto_tipo: TipoDesconto; desconto_valor: string; total_bruto: string; desconto_itens: string; subtotal: string; desconto_geral: string; total: string }
export interface PreviaBeneficio { comanda_id: string; versao: number; anterior: EstadoBeneficios; posterior: EstadoBeneficios; recebido_liquido: string; saldo: string; exige_fechamento: boolean; exige_gratuidade: boolean; conferencia: string }
export interface ResultadoBeneficio extends PreviaBeneficio { acao: Beneficio['acao']; item_id: string | null; motivo: string; registrado_por: string; registrado_em: string; chave_idempotencia: string; fechado: boolean }
export interface BeneficioPendente { chave: string; payload: Beneficio & { conferencia: string; confirmar_fechamento: boolean; confirmar_gratuidade: boolean } }
export const podeBeneficiar = (u: UsuarioLogado, c: Comanda) => podeAjustar(u, c);
export const chaveBeneficio = (id: string, c: Comanda) => `relaxabarber:beneficios:v1:${id}:${c.filial_id}:${c.id}`;

function validar(p: BeneficioPendente) {
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  if (!p || Object.keys(p).sort().join() !== 'chave,payload' || !uuid.test(p.chave) || !p.payload) throw Error('Benefício pendente inválido. Preserve o registro.');
  const d = p.payload;
  if (Object.keys(d).some(k => !['acao','versao','motivo','item_id','desconto_tipo','desconto_valor','conferencia','confirmar_fechamento','confirmar_gratuidade'].includes(k))
    || !['item','comanda','encerramento_gratuito'].includes(d.acao) || !Number.isInteger(d.versao) || d.versao < 0
    || typeof d.motivo !== 'string' || !d.motivo.trim() || d.motivo.length > 1000 || !/^[0-9a-f]{64}$/.test(d.conferencia)
    || typeof d.confirmar_fechamento !== 'boolean' || typeof d.confirmar_gratuidade !== 'boolean'
    || (d.acao === 'item' ? !uuid.test(d.item_id ?? '') : d.item_id !== undefined)) throw Error('Benefício pendente inválido. Preserve o registro.');
  const tipo = d.desconto_tipo ?? 'nenhum', valor = d.desconto_valor ?? '0.00';
  if (!['nenhum','valor','percentual','cortesia'].includes(tipo) || !/^\d{1,8}(\.\d{1,2})?$/.test(valor)
    || (tipo === 'percentual' && Number(valor) > 100) || (['nenhum','cortesia'].includes(tipo) && Number(valor) !== 0)
    || (tipo === 'cortesia' && d.acao !== 'item') || (d.acao === 'encerramento_gratuito' && (tipo !== 'nenhum' || Number(valor) !== 0))) throw Error('Benefício pendente inválido. Preserve o registro.');
}
export function lerBeneficio(key: string): BeneficioPendente | null { const raw = sessionStorage.getItem(key); if (!raw) return null; const p = JSON.parse(raw); validar(p); return p; }
export function salvarBeneficio(key: string, p: BeneficioPendente) { validar(p); const anterior = lerBeneficio(key); if (anterior && JSON.stringify(anterior) !== JSON.stringify(p)) throw Error('Recupere o benefício original antes de iniciar outro.'); sessionStorage.setItem(key, JSON.stringify(p)); }
export function limparBeneficio(key: string, p: BeneficioPendente) { if (JSON.stringify(lerBeneficio(key)) === JSON.stringify(p)) sessionStorage.removeItem(key); }
export async function previaBeneficio(c: Comanda, body: Beneficio): Promise<PreviaBeneficio> { return (await api.post(`/comandas/${c.id}/beneficios/previa`, body, { params: { filial_id: c.filial_id } })).data; }
export async function aplicarBeneficio(c: Comanda, p: BeneficioPendente): Promise<ResultadoBeneficio> { validar(p); return (await api.post(`/comandas/${c.id}/beneficios`, p.payload, { params: { filial_id: c.filial_id }, headers: { 'Idempotency-Key': p.chave } })).data; }
export async function historicoBeneficios(c: Comanda, signal: AbortSignal): Promise<ResultadoBeneficio[]> { return (await api.get(`/comandas/${c.id}/beneficios`, { params: { filial_id: c.filial_id }, signal })).data; }
