import api from './api';
import type { Comanda } from './comandas';
import type { UsuarioLogado } from './usuario';

export interface PagamentoHistorico { id: string; valor: string; forma: 'dinheiro' | 'pix' | 'debito' | 'credito'; recebido_em: string; registrado_em: string }
export interface EstornoHistorico { id: string; pagamento_id: string; valor: string; motivo: string; efetivado_em: string; registrado_em: string }
export interface HistoricoFinanceiro { pagamentos: PagamentoHistorico[]; estornos: EstornoHistorico[] }
export interface ResumoFinanceiro {
  comanda_id: string; filial_id: string; situacao: 'nao_verificado' | 'aberto' | 'fechado';
  total: string; pagamentos: string | null; estornos: string | null; recebido_liquido: string | null; saldo: string | null;
  historico: HistoricoFinanceiro;
  habilitacao?: { origem: 'portal_cliente'; conferencia: string; total: string; situacao: string; itens: { id: string; servico: string; descricao: string; quantidade: number; preco: string }[] } | null;
  habilitado_por?: string | null; habilitado_em?: string | null;
}
export const formasPagamento = { dinheiro: 'Dinheiro', pix: 'Pix', debito: 'Débito', credito: 'Crédito' };
export function pagamentosComEstornos(historico: HistoricoFinanceiro) {
  return historico.pagamentos.map((pagamento) => {
    const estornos = historico.estornos.filter((estorno) => estorno.pagamento_id === pagamento.id);
    const estornado = estornos.reduce((soma, estorno) => soma + centavos(estorno.valor), 0);
    const liquido = centavos(pagamento.valor) - estornado;
    return { ...pagamento, estornos, estornado: decimal(estornado), liquido: decimal(liquido) };
  });
}
export type Operacao = 'pagamentos' | 'recebimentos' | 'estornos' | 'fechamento-financeiro' | 'habilitacao-financeira';
export type FormaPagamento = keyof typeof formasPagamento;
export interface PagamentoConfirmado { valor: string; forma: FormaPagamento; recebido_em: string; confirmado: true }
export interface FechamentoPayload { motivo?: string | null; pagamentos?: PagamentoConfirmado[] }
export interface RecebimentosPayload { pagamentos: PagamentoConfirmado[] }
export interface EstornoPayload { pagamento_id: string; valor: string; motivo: string; efetivado_em: string }
export interface PagamentoLegado { valor: string; forma: FormaPagamento; recebido_em: string }
export interface HabilitacaoPayload { conferencia: string; confirmado: true; motivo: string }
export type Intencao = { operacao: 'recebimentos'; payload: RecebimentosPayload } | { operacao: 'fechamento-financeiro'; payload: FechamentoPayload } | { operacao: 'estornos'; payload: EstornoPayload } | { operacao: 'habilitacao-financeira'; payload: HabilitacaoPayload };
export type NovaPendente = Intencao & { chave: string };
export type Pendente = NovaPendente | { chave: string; operacao: 'pagamentos'; payload: PagamentoLegado };
export interface ParcelaFormulario { valor: string; forma: FormaPagamento; confirmado: boolean }
export interface Registro { id: string; valor: string; forma?: string; recebido_em?: string; efetivado_em?: string; pagamento_id?: string; motivo?: string }
export interface FechamentoRegistrado { comanda_id: string; filial_id: string; total: string; recebido_liquido: string; motivo: string | null; registrado_em: string; registrado_por: string; chave_idempotencia: string }
export interface HabilitacaoRegistrada { comanda_id: string; filial_id: string; motivo: string; registrado_em: string; registrado_por: string; chave_idempotencia: string }
export function centavos(valor: string): number {
  if (!/^\d{1,8}([.,]\d{1,2})?$/.test(valor)) throw new Error('Informe um valor válido com até duas casas decimais.');
  const [inteiro, fracao = ''] = valor.replace(',', '.').split('.');
  return Number(inteiro) * 100 + Number(fracao.padEnd(2, '0'));
}
export function decimal(valor: number): string { return `${Math.floor(valor / 100)}.${String(valor % 100).padStart(2, '0')}`; }
export function podeConsultar(usuario: Pick<UsuarioLogado, 'id' | 'perfil'>, comanda: Comanda): boolean {
  return ['admin', 'recepcao'].includes(usuario.perfil) || (['barbeiro', 'barbeiro_chefe'].includes(usuario.perfil) && usuario.id === comanda.barbeiro_id);
}
export function podeMovimentar(comanda: Comanda, resumo: ResumoFinanceiro): boolean {
  return ['aberta', 'fechada'].includes(comanda.status) && ['pendente', 'aguardando', 'em_atendimento', 'concluido'].includes(comanda.atendimento.status) && resumo.situacao === 'aberto';
}
export function dataEfetiva(valor: string, admin: boolean, minimo?: string): string {
  const data = new Date(valor);
  const agora = Date.now();
  if (!valor || !Number.isFinite(data.getTime()) || data.getTime() > agora) throw new Error('Informe uma data/hora válida, sem estar no futuro.');
  if (!admin && agora - data.getTime() > 168 * 3600000) throw new Error('Recebimentos retroativos são limitados às últimas 168 horas para seu perfil.');
  if (minimo && data < new Date(minimo)) throw new Error('O estorno não pode anteceder o recebimento original.');
  return data.toISOString();
}
export function agoraLocal(): string {
  const data = new Date();
  return new Date(data.getTime() - data.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export function prepararFechamento(resumo: ResumoFinanceiro, parcelas: ParcelaFormulario[], data: string, motivo: string, admin: boolean): FechamentoPayload {
  if (resumo.situacao !== 'aberto' || resumo.saldo === null || resumo.recebido_liquido === null) throw new Error('Consulte um histórico financeiro verificado e aberto antes de fechar.');
  const restante = centavos(resumo.saldo);
  if (parcelas.length > 16 || (!parcelas.length && restante > 0)) throw new Error('Informe de 1 a 16 recebimentos para quitar o valor restante.');
  const pagamentos = parcelas.map((parcela) => {
    const quantia = centavos(parcela.valor);
    if (quantia <= 0 || !Object.hasOwn(formasPagamento, parcela.forma)) throw new Error('Informe valor positivo e uma forma de pagamento válida.');
    if (parcela.confirmado !== true) throw new Error('Confirme o recebimento de cada valor antes de fechar.');
    return { valor: decimal(quantia), forma: parcela.forma, recebido_em: dataEfetiva(data, admin), confirmado: true as const };
  });
  if (pagamentos.reduce((soma, p) => soma + centavos(p.valor), 0) !== restante) throw new Error('A soma dos recebimentos deve ser exatamente igual ao valor restante. Não é permitido deixar saldo pendente.');
  if (centavos(resumo.total) === 0 && !motivo.trim()) throw new Error('Informe o motivo do fechamento com total zero.');
  return { motivo: motivo.trim() || null, pagamentos };
}
export function prepararRecebimentos(resumo: ResumoFinanceiro, parcelas: ParcelaFormulario[], data: string, admin: boolean): RecebimentosPayload {
  if (resumo.situacao !== 'aberto' || resumo.saldo === null || centavos(resumo.saldo) <= 0) throw new Error('Consulte uma comanda aberta com saldo pendente.');
  if (!parcelas.length || parcelas.length > 16) throw new Error('Informe de 1 a 16 recebimentos confirmados.');
  const pagamentos = parcelas.map((p) => {
    const valor = centavos(p.valor);
    if (valor <= 0 || !Object.hasOwn(formasPagamento, p.forma)) throw new Error('Informe valor positivo e forma de pagamento válida.');
    if (p.confirmado !== true) throw new Error('Confirme que cada valor foi efetivamente recebido. Pix exibido ou prometido não é pagamento.');
    return { valor: decimal(valor), forma: p.forma, recebido_em: dataEfetiva(data, admin), confirmado: true as const };
  });
  if (pagamentos.reduce((s, p) => s + centavos(p.valor), 0) > centavos(resumo.saldo)) throw new Error('O recebimento não pode exceder o saldo pendente.');
  return { pagamentos };
}
export function chaveStorage(usuario: string, comanda: Comanda): string { return `relaxabarber:financeiro:v1:${usuario}:${comanda.filial_id}:${comanda.id}`; }
function objeto(dado: unknown): dado is Record<string, unknown> { return !!dado && typeof dado === 'object' && !Array.isArray(dado); }
function campos(dado: Record<string, unknown>, permitidos: string[], obrigatorios = permitidos): boolean {
  return Object.keys(dado).every((campo) => permitidos.includes(campo)) && obrigatorios.every((campo) => Object.hasOwn(dado, campo));
}
function dinheiroValido(valor: unknown): valor is string {
  return typeof valor === 'string' && /^\d{1,8}(\.\d{1,2})?$/.test(valor) && centavos(valor) > 0;
}
function dataValida(valor: unknown): valor is string {
  // Recuperação não revalida janela relativa: preservar exatamente o timestamp original.
  return typeof valor === 'string' && /T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/i.test(valor) && Number.isFinite(new Date(valor).getTime());
}
function pagamentoValido(p: unknown): p is PagamentoLegado {
  return objeto(p) && campos(p, ['valor', 'forma', 'recebido_em']) && dinheiroValido(p.valor) && typeof p.forma === 'string' && Object.hasOwn(formasPagamento, p.forma) && dataValida(p.recebido_em);
}
function validarPendente(dado: unknown): Pendente {
  if (!objeto(dado) || !campos(dado, ['chave', 'operacao', 'payload']) || typeof dado.chave !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(dado.chave) || !objeto(dado.payload)) throw new Error('Operação pendente inválida. Preserve o registro e procure o administrador.');
  const p = dado.payload;
  let valido = false;
  if (dado.operacao === 'habilitacao-financeira') valido = campos(p, ['conferencia', 'confirmado', 'motivo']) && typeof p.conferencia === 'string' && /^[0-9a-f]{64}$/.test(p.conferencia) && p.confirmado === true && typeof p.motivo === 'string' && !!p.motivo.trim() && p.motivo.length <= 1000;
  if (dado.operacao === 'pagamentos') valido = pagamentoValido(p);
  if (dado.operacao === 'recebimentos') valido = campos(p, ['pagamentos']) && Array.isArray(p.pagamentos) && p.pagamentos.length >= 1 && p.pagamentos.length <= 16 && p.pagamentos.every((pagamento) => {
    if (!objeto(pagamento) || !campos(pagamento, ['valor', 'forma', 'recebido_em', 'confirmado']) || pagamento.confirmado !== true) return false;
    return pagamentoValido({ valor: pagamento.valor, forma: pagamento.forma, recebido_em: pagamento.recebido_em });
  });
  if (dado.operacao === 'estornos') valido = campos(p, ['pagamento_id', 'valor', 'motivo', 'efetivado_em']) && typeof p.pagamento_id === 'string' && !!p.pagamento_id && dinheiroValido(p.valor) && typeof p.motivo === 'string' && !!p.motivo.trim() && dataValida(p.efetivado_em);
  if (dado.operacao === 'fechamento-financeiro') {
    valido = campos(p, ['motivo', 'pagamentos'], []) && (!Object.hasOwn(p, 'motivo') || p.motivo === null || (typeof p.motivo === 'string' && !!p.motivo.trim()));
    if (Object.hasOwn(p, 'pagamentos')) valido = valido && Array.isArray(p.pagamentos) && p.pagamentos.length <= 16 && p.pagamentos.every((pagamento) => {
      if (!objeto(pagamento) || !campos(pagamento, ['valor', 'forma', 'recebido_em', 'confirmado']) || pagamento.confirmado !== true) return false;
      const { valor, forma, recebido_em } = pagamento;
      return pagamentoValido({ valor, forma, recebido_em });
    });
  }
  if (!valido) throw new Error('Dados pendentes inválidos. Preserve o registro e procure o administrador.');
  return dado as unknown as Pendente;
}
export function lerPendente(chave: string): Pendente | null {
  const valor = sessionStorage.getItem(chave);
  if (!valor) return null;
  return validarPendente(JSON.parse(valor));
}
export function salvarPendente(chave: string, pendente: Pendente): void {
  validarPendente(pendente);
  const anterior = lerPendente(chave);
  if ((anterior && JSON.stringify(anterior) !== JSON.stringify(pendente)) || (pendente.operacao === 'pagamentos' && !anterior)) throw new Error('Resolva a operação original antes de iniciar outra.');
  sessionStorage.setItem(chave, JSON.stringify(pendente));
}
export function limparPendente(chave: string, pendente: Pendente): void {
  if (JSON.stringify(lerPendente(chave)) === JSON.stringify(pendente)) sessionStorage.removeItem(chave);
}
export async function consultarFinanceiro(comanda: Comanda, signal?: AbortSignal): Promise<ResumoFinanceiro> {
  return (await api.get<ResumoFinanceiro>(`/comandas/${encodeURIComponent(comanda.id)}/financeiro`, { params: { filial_id: comanda.filial_id }, signal })).data;
}
async function postarFinanceiro(comanda: Comanda, pendente: Pendente): Promise<Registro | Registro[] | FechamentoRegistrado | HabilitacaoRegistrada> {
  validarPendente(pendente);
  return (await api.post<Registro | FechamentoRegistrado>(`/comandas/${encodeURIComponent(comanda.id)}/${pendente.operacao}`, pendente.payload, { params: { filial_id: comanda.filial_id }, headers: { 'Idempotency-Key': pendente.chave } })).data;
}
export async function enviarFinanceiro(comanda: Comanda, pendente: NovaPendente): Promise<Registro | Registro[] | FechamentoRegistrado | HabilitacaoRegistrada> {
  if ((pendente as Pendente).operacao === 'pagamentos') throw new Error('Use a operação de recebimentos confirmados para novos registros.');
  return postarFinanceiro(comanda, pendente);
}
export async function recuperarFinanceiro(comanda: Comanda, storage: string): Promise<Registro | Registro[] | FechamentoRegistrado | HabilitacaoRegistrada> {
  if (!storage.endsWith(`:${comanda.filial_id}:${comanda.id}`)) throw new Error('Pendência de outra comanda ou filial.');
  const pendente = lerPendente(storage);
  if (!pendente) throw new Error('Operação original não encontrada.');
  return postarFinanceiro(comanda, pendente);
}
export function erroFinanceiro(erro: unknown): string {
  const resposta = (erro as { response?: { status: number; data?: { detail?: { codigo?: string } } } })?.response;
  if (resposta?.status === 403) return 'Sem permissão financeira para esta comanda.';
  if (resposta?.status === 404) return 'Comanda não encontrada ou indisponível para seu acesso.';
  if (resposta?.status === 401) return 'Sessão expirada. Entre novamente para consultar ou recuperar a operação.';
  const codigo = resposta?.data?.detail?.codigo;
  const mensagens: Record<string, string> = {
    entrada_financeira_invalida: 'Verifique valor, motivo e data/hora: timezone obrigatório, sem futuro e retroatividade de até 168 horas para não administradores.',
    historico_financeiro_nao_verificado: 'Histórico não verificado. É necessária conciliação específica.',
    estado_financeiro_incompativel: 'O estado atual não permite esta operação. Consulte o financeiro.',
    saldo_insuficiente: 'O saldo atual não permite este valor ou fechamento. Consulte o financeiro.',
    limite_estorno_excedido: 'O valor excede o limite disponível deste pagamento.',
    conflito_idempotencia: 'Conflito na chave da operação. Preserve o registro pendente e procure o administrador.',
  };
  return (codigo && mensagens[codigo]) || (resposta?.status === 422 ? 'Dados inválidos. Verifique valor, motivo e data/hora.' : 'Não foi possível confirmar a operação. Consulte o estado e repita com a mesma chave e os mesmos dados.');
}
export function resultadoIncerto(erro: unknown): boolean {
  const resposta = (erro as { response?: { status: number; data?: { detail?: { codigo?: string } } } })?.response;
  return !resposta || resposta.status >= 500 || resposta.data?.detail?.codigo === 'conflito_idempotencia';
}
