import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../services/api';
import { EVENTO_ESTOQUE_ATUALIZADO } from '../services/eventosEstoque';
import { quantidade } from '../pages/estoque/estoqueUtils';
import { Icone } from './Icone';

interface AlertaEstoque {
  id: string;
  nome: string;
  unidade: string;
  saldo: string;
  estoque_minimo: string;
}

export function AlertasEstoque({ filialId }: { filialId: string }) {
  const [alertas, setAlertas] = useState<AlertaEstoque[] | null>(null);
  const [erro, setErro] = useState(false);
  const [tentativa, setTentativa] = useState(0);

  useEffect(() => {
    let requisicao: AbortController | undefined;
    let pendente = false;

    async function atualizar() {
      if (document.hidden) return;
      if (requisicao) { pendente = true; return; }
      const atual = new AbortController();
      requisicao = atual;
      try {
        const { data } = await api.get<AlertaEstoque[]>('/estoque/alertas', {
          params: { filial_id: filialId }, signal: atual.signal,
        });
        if (!atual.signal.aborted) { setAlertas(data); setErro(false); }
      } catch {
        if (!atual.signal.aborted) setErro(true);
      } finally {
        requisicao = undefined;
        if (pendente && !atual.signal.aborted) { pendente = false; void atualizar(); }
      }
    }

    void atualizar();
    const timer = window.setInterval(atualizar, 15000);
    window.addEventListener(EVENTO_ESTOQUE_ATUALIZADO, atualizar);
    window.addEventListener('focus', atualizar);
    document.addEventListener('visibilitychange', atualizar);
    return () => {
      requisicao?.abort();
      window.clearInterval(timer);
      window.removeEventListener(EVENTO_ESTOQUE_ATUALIZADO, atualizar);
      window.removeEventListener('focus', atualizar);
      document.removeEventListener('visibilitychange', atualizar);
    };
  }, [filialId, tentativa]);

  const total = alertas?.length ?? 0;
  return <details aria-label="Alertas de estoque" className="mb-4 max-w-xl rounded-lg border border-outline/40 bg-surface-container p-3">
    <summary className="cursor-pointer font-semibold">
      <span className="inline-flex flex-wrap items-center gap-2 align-middle">
        <Icone nome="inventory_2" /> Alertas de estoque
        <span role="status" className={total ? 'rounded-full bg-primary-container px-2 text-on-primary-container' : 'text-on-surface-variant'}>
          {erro ? 'Atualização indisponível' : alertas === null ? 'Consultando…' : `${total} ${total === 1 ? 'ativo' : 'ativos'}`}
        </span>
      </span>
    </summary>
    {erro && <p className="mt-2">Não foi possível atualizar os alertas.{' '}
      <button type="button" className="underline" onClick={() => setTentativa(n => n + 1)}>Tentar novamente</button>
    </p>}
    {total > 0 ? <ul className="mt-2 max-h-64 divide-y divide-outline/30 overflow-y-auto">
      {alertas?.map(item => <li key={item.id} className="py-2">
        <strong className="break-words">{item.nome}</strong>
        <p className="text-sm text-on-surface-variant">Saldo atual {quantidade(item.saldo)} {item.unidade} · Mínimo {quantidade(item.estoque_minimo)} {item.unidade}</p>
      </li>)}
    </ul> : !erro && alertas !== null && <p className="mt-2 text-sm">Nenhum item atingiu o estoque mínimo.</p>}
    <Link to="/estoque" className="mt-2 inline-block underline">Abrir estoque</Link>
  </details>;
}
