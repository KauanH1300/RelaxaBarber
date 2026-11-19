import { useEffect, useState } from 'react';
import { barbeirosPublicos, horariosPublicos } from '../../services/agendamentoPublico';
import type { ProfissionalPublico } from '../../services/agendamentoPublico';
import { mensagemErro } from '../../services/erros';

export function useAgendaPublica(filial: string, servico: string, barbeiro: string, data: string, revisao = 0) {
  const [equipe, setEquipe] = useState<{ key: string; itens: ProfissionalPublico[]; erro?: string }>({ key: '', itens: [] });
  const [agenda, setAgenda] = useState<{ key: string; horarios: string[]; erro?: string }>({ key: '', horarios: [] });
  const chaveEquipe = `${filial}:${servico}`;
  const key = `${chaveEquipe}:${barbeiro}:${data}:${revisao}`;
  useEffect(() => {
    if (!filial || !servico) return;
    const c = new AbortController();
    barbeirosPublicos(filial, servico.split(','), c.signal).then(itens => { if (!c.signal.aborted) setEquipe({ key: chaveEquipe, itens }); })
      .catch(e => { if (!c.signal.aborted) setEquipe({ key: chaveEquipe, itens: [], erro: mensagemErro(e, 'Não foi possível consultar os profissionais.') }); });
    return () => c.abort();
  }, [filial, servico, chaveEquipe]);
  useEffect(() => {
    if (!filial || !servico || !barbeiro || !data) return;
    const c = new AbortController();
    horariosPublicos(filial, servico.split(','), data, barbeiro, c.signal).then(a => { if (!c.signal.aborted) setAgenda({ key, horarios: a.horarios }); })
      .catch(e => { if (!c.signal.aborted) setAgenda({ key, horarios: [], erro: mensagemErro(e, 'Não foi possível consultar os horários.') }); });
    return () => c.abort();
  }, [filial, servico, barbeiro, data, key]);
  return { equipe: equipe.key === chaveEquipe ? equipe : null, agenda: agenda.key === key ? agenda : null };
}
