import api from './api';

export interface CategoriaServico { id: string; nome: string }

export interface Servico {
  id: string;
  nome: string;
  preco: number;
  tempo_estimado: number;
  ativo: boolean;
  categorias?: CategoriaServico[];
}

export interface ServicoAdministrativo extends Servico {
  comissao_padrao: number;
}

export type ServicoInput = Omit<ServicoAdministrativo, 'id' | 'ativo' | 'categorias'> & { categorias_ids?: string[] };

// Usado somente na tela administrativa, protegida por SomenteAdministrador.
export const consultarServico = (id: string) => api.get<ServicoAdministrativo>(`/servicos/${id}`);

export const listarServicos = () => api.get<Servico[]>('/servicos/');
export const criarServico = (dados: ServicoInput, chave?: string) => api.post<ServicoAdministrativo>('/servicos/', dados,
  chave ? { headers: { 'Idempotency-Key': chave } } : undefined);
export const conferirCadastroServico = (chave: string) =>
  api.get<ServicoAdministrativo>(`/servicos/cadastros/${encodeURIComponent(chave)}`);
export const atualizarServico = (id: string, dados: Partial<ServicoInput>) =>
  api.put<ServicoAdministrativo>(`/servicos/${id}`, dados);
export const excluirServico = (id: string) => api.delete(`/servicos/${id}`);

export const listarCategoriasServico = (signal?: AbortSignal) =>
  api.get<CategoriaServico[]>('/servicos/categorias', { signal });
export const criarCategoriaServico = (nome: string) =>
  api.post<CategoriaServico>('/servicos/categorias', { nome });
