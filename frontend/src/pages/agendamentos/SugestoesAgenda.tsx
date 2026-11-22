import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { contextoValido } from '../../services/filialAtiva';
import type { MarcaContexto } from '../../services/filialAtiva';
import { mensagemErro } from '../../services/erros';

type Sugestao = { hora_inicio: string; barbeiro_id: string; barbeiro: string };
type Props = {
  marca: MarcaContexto;
  data: string;
  duracao?: number;
  servicos?: string[];
  agendamentoId?: string;
  onEscolher: (sugestao: Sugestao) => void;
};

export function SugestoesAgenda({ marca, data, duracao, servicos, agendamentoId, onEscolher }: Props) {
  const [sugestoes, setSugestoes] = useState<Sugestao[] | null>(null);
  const [erro, setErro] = useState('');
  const [consultando, setConsultando] = useState(false);
  const requisicao = useRef<AbortController | null>(null);
  useEffect(() => () => requisicao.current?.abort(), []);

  async function consultar() {
    if (requisicao.current || !marca.filialId || !contextoValido(marca)) return;
    const controller = new AbortController();
    requisicao.current = controller;
    setConsultando(true);
    setErro('');
    setSugestoes(null);
    const params = { data, filial_id: marca.filialId, duracao_min: duracao,
      agendamento_id: agendamentoId, servicos_ids: servicos };
    try {
      const resposta = await api.get<Sugestao[]>('/agendamentos/sugestoes', {
        params, paramsSerializer: { indexes: null }, signal: controller.signal,
      });
      if (!controller.signal.aborted && contextoValido(marca)) setSugestoes(resposta.data);
    } catch (falha) {
      if (!controller.signal.aborted && contextoValido(marca)) setErro(mensagemErro(falha, 'Não foi possível consultar sugestões.'));
    } finally {
      requisicao.current = null;
      if (!controller.signal.aborted) setConsultando(false);
    }
  }

  const duracaoValida = duracao === undefined || (Number.isInteger(duracao) && duracao >= 1 && duracao <= 480);
  return <section aria-label="Sugestões de horários">
    <button type="button" disabled={consultando || !data || !duracaoValida || (!agendamentoId && !servicos?.length)}
      onClick={() => void consultar()}>
      {consultando ? 'Buscando horários…' : sugestoes ? 'Atualizar sugestões' : 'Sugerir horários'}
    </button>
    {erro && <p role="alert">{erro}</p>}
    {sugestoes?.length === 0 && <p role="status">Nenhum horário sugerido para esta data. Você pode consultar outra data ou preencher o horário manualmente.</p>}
    {!!sugestoes?.length && <ul>{sugestoes.map(s =>
      <li key={s.barbeiro_id + s.hora_inicio}>
        <button type="button" onClick={() => onEscolher(s)}>{s.hora_inicio} · {s.barbeiro}</button>
      </li>
    )}</ul>}
  </section>;
}
