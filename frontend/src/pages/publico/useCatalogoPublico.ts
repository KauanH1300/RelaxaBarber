import { useEffect, useState } from 'react';
import { catalogoPublico } from '../../services/agendamentoPublico';
import type { Servico } from '../../services/servico';

export function useCatalogoPublico() {
  const [servicos, setServicos] = useState<Servico[]>([]); const [estado, setEstado] = useState<'carregando' | 'pronto' | 'erro'>('carregando');
  useEffect(() => {
    const controller = new AbortController();
    catalogoPublico(controller.signal).then(data => { if (!controller.signal.aborted) { setServicos(data); setEstado('pronto'); } })
      .catch(() => { if (!controller.signal.aborted) setEstado('erro'); });
    return () => controller.abort();
  }, []);
  return { servicos, estado };
}
export const precoPublico = (valor: number) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(valor));
