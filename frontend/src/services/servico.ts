import api from './api';

export interface Servico {
  id: string;
  nome: string;
  preco: number;
  tempo_estimado: number;
  ativo: boolean;
}

export interface ServicoAdministrativo extends Servico {
  comissao_padrao: number;
}

export type ServicoInput = Omit<ServicoAdministrativo, 'id' | 'ativo'>;

// Usado somente na tela administrativa, protegida por SomenteAdministrador.
export const consultarServico = (id: string) => api.get<ServicoAdministrativo>(`/servicos/${id}`);

export const listarServicos = () => api.get<Servico[]>('/servicos/');
export const criarServico = (dados: ServicoInput) => api.post<ServicoAdministrativo>('/servicos/', dados);
export const atualizarServico = (id: string, dados: Partial<ServicoInput>) =>
  api.put<ServicoAdministrativo>(`/servicos/${id}`, dados);
export const excluirServico = (id: string) => api.delete(`/servicos/${id}`);
