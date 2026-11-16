import { useEffect, useState } from 'react';
import { barbeirosPublicos, horariosPublicos } from '../../services/agendamentoPublico';
import type { ProfissionalPublico } from '../../services/agendamentoPublico';
import { mensagemErro } from '../../services/erros';

export function useAgendaPublica(servico: string, barbeiro: string, data: string, revisao = 0) {
  const [equipe, setEquipe] = useState<{ key: string; itens: ProfissionalPublico[]; erro?: string }>({ key: '', itens: [] });
  const [agenda, setAgenda] = useState<{ key: string; horarios: string[]; erro?: string }>({ key: '', horarios: [] });
  const key = `${servico}:${barbeiro}:${data}:${revisao}`;
  useEffect(() => {
    if (!servico) return;
    const c = new AbortController();
    barbeirosPublicos(servico, c.signal).then(itens => { if (!c.signal.aborted) setEquipe({ key: servico, itens }); })
      .catch(e => { if (!c.signal.aborted) setEquipe({ key: servico, itens: [], erro: mensagemErro(e, 'Não foi possível consultar os profissionais.') }); });
    return () => c.abort();
  }, [servico]);
  useEffect(() => {
    if (!servico || !barbeiro || !data) return;
    const c = new AbortController();
    horariosPublicos(servico, data, barbeiro, c.signal).then(a => { if (!c.signal.aborted) setAgenda({ key, horarios: a.horarios }); })
      .catch(e => { if (!c.signal.aborted) setAgenda({ key, horarios: [], erro: mensagemErro(e, 'Não foi possível consultar os horários.') }); });
    return () => c.abort();
  }, [servico, barbeiro, data, key]);
  return { equipe: equipe.key === servico ? equipe : null, agenda: agenda.key === key ? agenda : null };
}
