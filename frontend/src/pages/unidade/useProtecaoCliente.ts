import { useEffect } from 'react';

export function useProtecaoCliente(pendente: boolean, filialId: string | null) {
  useEffect(() => {
    if (!pendente) return;
    const sair = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const navegar = (event: MouseEvent) => {
      if (!(event.target instanceof Element) || !event.target.closest('a[href], button[title="Sair"]')) return;
      if (!window.confirm('Há alterações de cliente não salvas ou uma operação a conferir. Sair desta tela? O rascunho será mantido nesta sessão do navegador.')) {
        event.preventDefault(); event.stopPropagation();
      }
    };
    const trocar = (event: Event) => {
      if (!(event.target instanceof HTMLSelectElement) || event.target.getAttribute('aria-label') !== 'Filial ativa') return;
      if (!window.confirm('Há alterações de cliente não salvas. Trocar de filial? O rascunho ficará na filial de origem.')) {
        event.stopPropagation(); event.target.value = filialId ?? '';
      }
    };
    window.addEventListener('beforeunload', sair);
    document.addEventListener('click', navegar, true);
    document.addEventListener('change', trocar, true);
    return () => { window.removeEventListener('beforeunload', sair); document.removeEventListener('click', navegar, true); document.removeEventListener('change', trocar, true); };
  }, [pendente, filialId]);
}
