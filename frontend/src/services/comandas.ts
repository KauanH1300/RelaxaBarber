import api from './api';
import { mensagemErro } from './erros';

export type StatusComanda = 'pendente' | 'aberta' | 'fechada' | 'cancelada';
export const statusComanda: Record<StatusComanda, string> = {
  pendente: 'Pendente', aberta: 'Aberta', fechada: 'Fechada', cancelada: 'Cancelada',
};
export const statusAtendimento: Record<string, string> = {
  pendente: 'Agendado', aguardando: 'Aguardando atendimento', em_atendimento: 'Em atendimento',
  concluido: 'Concluído', cancelado: 'Cancelado',
};
export interface PessoaComanda { id: string; nome: string }
export interface ItemComanda {
  id: string; tipo: string; servico_id: string | null; descricao: string;
  quantidade: number; preco_unitario: string; subtotal: string;
}
export interface Comanda {
  id: string; agendamento_id: string; filial_id: string; cliente_id: string; barbeiro_id: string;
  status: StatusComanda; data_abertura: string | null; data_fechamento: string | null;
  cliente: PessoaComanda; profissional: PessoaComanda; filial: PessoaComanda;
  atendimento: { id: string; data: string; hora_inicio: string; hora_fim: string; status: string };
  itens: ItemComanda[]; total: string;
}
export interface IndicadoresComanda {
  contagens: Record<StatusComanda, number>; valor_abertas: string; pagamentos_disponiveis: false;
}
export interface PainelComandas {
  itens: Comanda[]; total: number; pagina: number; tamanho: number; indicadores: IndicadoresComanda;
}
export interface FiltrosComanda {
  busca: string; profissional_id: string; data_inicio: string; data_fim: string;
  status: StatusComanda | '';
}

export async function consultarComandas(filtros: FiltrosComanda, pagina: number, signal?: AbortSignal): Promise<PainelComandas> {
  const params = Object.fromEntries(Object.entries({ ...filtros, pagina, tamanho: 6 }).filter(([, valor]) => valor !== ''));
  return (await api.get<PainelComandas>('/comandas/painel', { params, signal })).data;
}
export async function detalharComanda(id: string, signal?: AbortSignal): Promise<Comanda> {
  return (await api.get<Comanda>(`/comandas/${encodeURIComponent(id)}`, { signal })).data;
}
export function erroConsultaComanda(erro: unknown, detalhe = false): string {
  if (erro && typeof erro === 'object' && 'response' in erro) {
    const response = erro.response as { status?: number } | undefined;
    if (response?.status === 404) return 'Comanda não encontrada ou indisponível para seu acesso.';
    if (response?.status === 403) return 'Seu acesso a esta unidade não está disponível. Atualize as unidades no menu.';
  }
  return mensagemErro(erro, detalhe ? 'Não foi possível carregar os detalhes da comanda' : 'Não foi possível carregar as comandas');
}
export function identificarComanda(id: string): string {
  return `CMD · ${id.slice(0, 8)}…${id.slice(-4)}`;
}
export function moeda(valor: string): string {
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(valor));
}
export function diaRecife(agora = new Date()): string {
  const partes = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Recife', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(agora);
  const valor = (tipo: string) => partes.find((parte) => parte.type === tipo)?.value;
  return `${valor('year')}-${valor('month')}-${valor('day')}`;
}
export function dataAtendimento(data: string): string {
  const [ano, mes, dia] = data.split('-');
  return `${dia}/${mes}/${ano}`;
}
export function instanteRecife(valor: string | null): string {
  return valor ? new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Recife', dateStyle: 'short', timeStyle: 'short' }).format(new Date(valor)) : 'Não registrada';
}
export function intervaloPagina(pagina: number, tamanho: number, total: number): string {
  if (!total || (pagina - 1) * tamanho >= total) return '0';
  return `${(pagina - 1) * tamanho + 1}–${Math.min(pagina * tamanho, total)}`;
}
