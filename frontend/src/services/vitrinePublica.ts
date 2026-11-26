import { apiPublica } from './agendamentoPublico';

export interface ProdutoVitrine {
  nome: string;
  descricao: string | null;
  foto_url: string | null;
  preco: string;
  disponivel: boolean;
}

interface PaginaVitrine {
  produtos: ProdutoVitrine[];
  proxima_pagina: number | null;
}

export async function consultarVitrine(filial: string, pagina: number, signal: AbortSignal) {
  const { data } = await apiPublica.get<PaginaVitrine>(
    `/publico/filiais/${encodeURIComponent(filial)}/produtos`,
    { params: { pagina }, signal },
  );
  return data;
}
