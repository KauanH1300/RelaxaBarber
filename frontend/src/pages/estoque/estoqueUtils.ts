export type Produto = { id: string; nome: string; unidade: string; venda: boolean; consumo: boolean; categoria_id?: string | null; marca_id?: string | null; custo: string; preco_venda: string | null; comissao_padrao?: string | null; estoque_minimo: string; saldo: string; ativo: boolean; descricao_vitrine?: string | null; visivel_vitrine?: boolean; foto_url?: string | null };
export type Situacao = 'normal' | 'baixo' | 'esgotado' | 'inativo';
export function situacao(p: Produto): Situacao {
  if (!p.ativo) return 'inativo';
  if (Number(p.saldo) <= 0) return 'esgotado';
  return Number(p.saldo) <= Number(p.estoque_minimo) ? 'baixo' : 'normal';
}
export const rotulos: Record<Situacao, string> = { normal: 'Normal', baixo: 'Estoque baixo', esgotado: 'Esgotado', inativo: 'Inativo' };
export const moeda = (v: number | string) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
export const quantidade = (v: number | string) => Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 3 });
export function filtrar(produtos: Produto[], termo: string, finalidade: string, estado: string): Produto[] {
  const busca = termo.trim().toLocaleLowerCase('pt-BR');
  return produtos.filter(p => p.nome.toLocaleLowerCase('pt-BR').includes(busca) && (finalidade === 'todos' || (finalidade === 'venda' ? p.venda : p.consumo)) && (estado === 'todos' || situacao(p) === estado));
}
export function indicadores(produtos: Produto[]) {
  const ativos = produtos.filter(p => p.ativo);
  return { total: produtos.length, ativos: ativos.length, venda: produtos.filter(p => p.venda).length, consumo: produtos.filter(p => p.consumo).length, baixo: ativos.filter(p => situacao(p) === 'baixo').length, esgotado: ativos.filter(p => situacao(p) === 'esgotado').length, valor: ativos.reduce((s, p) => s + Number(p.custo) * Number(p.saldo), 0) };
}
function celula(v: string | number | null): string {
  let texto = String(v ?? '');
  // eslint-disable-next-line no-control-regex
  if (/^[\s\u0000-\u001f]*[=+\-@]/.test(texto)) texto = "'" + texto;
  return '"' + texto.replace(/"/g, '""') + '"';
}
export function csv(produtos: Produto[]): string {
  const linhas = [['Nome', 'Unidade', 'Venda', 'Consumo interno', 'Saldo', 'Estoque mínimo', 'Custo', 'Preço de venda', 'Situação'], ...produtos.map(p => [p.nome, p.unidade, p.venda ? 'Sim' : 'Não', p.consumo ? 'Sim' : 'Não', p.saldo, p.estoque_minimo, p.custo, p.preco_venda, rotulos[situacao(p)]])];
  return '\ufeff' + linhas.map(l => l.map(celula).join(';')).join('\r\n');
}
