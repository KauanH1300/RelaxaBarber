import { createContext, useContext } from 'react';
import type { Filial } from './filialAtiva';

export interface ContextoFilial {
  filiais: Filial[];
  filialId: string | null;
  versao: number;
  carregando: boolean;
  erro: string;
  selecionar: (id: string) => void;
  recarregar: () => void;
}
export const Contexto = createContext<ContextoFilial | null>(null);

export function useFilial(): ContextoFilial {
  const contexto = useContext(Contexto);
  if (!contexto) throw new Error('Contexto de filial ausente');
  return contexto;
}
