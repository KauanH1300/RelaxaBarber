export interface ResumoCliente {
  cliente_id: string;
  escopo_filiais: 'empresa' | 'filiais_autorizadas';
  escopo_profissional: 'todos' | 'proprio';
  parcial: boolean;
  atendimentos_concluidos: number;
  filiais: { filial_id: string; filial_nome: string; atendimentos_concluidos: number; total_gasto?: string | null }[];
  financeiro_disponivel?: boolean;
  total_gasto?: string | null;
}

export function descricaoEscopo(resumo: ResumoCliente): string {
  if (resumo.escopo_profissional === 'proprio') return 'Resumo parcial: somente seus atendimentos nas filiais autorizadas.';
  if (resumo.parcial || resumo.escopo_filiais !== 'empresa') return 'Resumo parcial: somente filiais autorizadas.';
  return 'Consolidado da RelaxaBarber, incluindo o histórico de filiais inativas.';
}
