import api from './api';
import type { Comanda } from './comandas';
import { podeConsultar } from './financeiro';
import type { UsuarioLogado } from './usuario';

export interface ServicoParaComanda { id: string; nome: string; preco: number; ativo: boolean }
export interface InclusaoPendente { chave: string; payload: { servico_id: string; quantidade: number } }
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function validar(p: InclusaoPendente): void {
  if (!p || Object.keys(p).sort().join() !== 'chave,payload' || !uuid.test(p.chave) || !p.payload || Object.keys(p.payload).sort().join() !== 'quantidade,servico_id' || !uuid.test(p.payload.servico_id) || !Number.isInteger(p.payload.quantidade) || p.payload.quantidade < 1 || p.payload.quantidade > 999) throw new Error('Registro de inclusão inválido. Preserve os dados e procure o administrador.');
}
export function chaveInclusao(usuario: string, comanda: Comanda): string { return `relaxabarber:itens:v1:${usuario}:${comanda.filial_id}:${comanda.id}`; }
export function lerInclusao(chave: string): InclusaoPendente | null {
  const raw = sessionStorage.getItem(chave);
  if (!raw) return null;
  const p = JSON.parse(raw) as InclusaoPendente; validar(p); return p;
}
export function salvarInclusao(chave: string, p: InclusaoPendente): void {
  validar(p);
  const antiga = lerInclusao(chave);
  if (antiga && JSON.stringify(antiga) !== JSON.stringify(p)) throw new Error('Recupere a inclusão original antes de iniciar outra.');
  sessionStorage.setItem(chave, JSON.stringify(p));
}
export function limparInclusao(chave: string, p: InclusaoPendente): void {
  if (JSON.stringify(lerInclusao(chave)) === JSON.stringify(p)) sessionStorage.removeItem(chave);
}
export function permiteInclusao(usuario: Pick<UsuarioLogado, 'id' | 'perfil'>, c: Comanda): boolean {
  return podeConsultar(usuario, c) && c.status === 'aberta' && c.atendimento.status !== 'cancelado' && ['aberta', 'pagamento_pendente', 'aguardando_fechamento'].includes(c.status_apresentacao ?? '');
}
export function motivoIndisponibilidadeInclusao(usuario: Pick<UsuarioLogado, 'id' | 'perfil'>, c: Comanda): string | null {
  // Explicar a mesma elegibilidade sem expor estado financeiro fora do escopo.
  if (!podeConsultar(usuario, c) || c.status_apresentacao === 'restrito') return 'Seu perfil não tem permissão para adicionar serviços nesta comanda.';
  if (c.status_apresentacao === 'fechada') return 'Comanda financeiramente fechada. Não é permitido adicionar serviços.';
  if (c.status === 'cancelada' || c.atendimento.status === 'cancelado') return 'Comanda ou atendimento cancelado. Não é permitido adicionar serviços.';
  if (c.status === 'fechada') return 'Comanda operacionalmente fechada. Esse estado histórico não comprova pagamento e não permite adicionar serviços.';
  if (c.status === 'pendente') return 'Comanda ainda pendente de abertura. Inicie o atendimento antes de adicionar serviços.';
  if (!c.status_apresentacao || c.status_apresentacao === 'nao_verificado') return 'Classificação financeira não verificada. Não é possível afirmar pagamento ou dívida; solicite a verificação antes de adicionar serviços.';
  if (!permiteInclusao(usuario, c)) return 'O estado atual da comanda não permite adicionar serviços. Atualize os detalhes antes de tentar novamente.';
  return null;
}
export async function catalogoItens(signal: AbortSignal): Promise<ServicoParaComanda[]> {
  return (await api.get<ServicoParaComanda[]>('/servicos/', { signal })).data.filter((s) => s.ativo);
}
export async function incluirServico(c: Comanda, p: InclusaoPendente): Promise<void> {
  validar(p);
  await api.post(`/comandas/${encodeURIComponent(c.id)}/itens/servicos`, p.payload, { params: { filial_id: c.filial_id }, headers: { 'Idempotency-Key': p.chave } });
}
