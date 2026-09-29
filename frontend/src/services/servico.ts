import api from './api';

export interface Servico {
  id: string;
  nome: string;
  preco: number;
  tempo_estimado: number;
  comissao_padrao: number;
  ativo: boolean;
}

export type ServicoInput = Omit<Servico, 'id' | 'ativo'>;

export const listarServicos = () => api.get<Servico[]>('/servicos/');
export const criarServico = (dados: ServicoInput) => api.post<Servico>('/servicos/', dados);
export const atualizarServico = (id: string, dados: Partial<ServicoInput>) =>
  api.put<Servico>(`/servicos/${id}`, dados);
export const excluirServico = (id: string) => api.delete(`/servicos/${id}`);