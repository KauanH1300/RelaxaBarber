import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import api from '../../services/api';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { mensagemErro } from '../../services/erros';

interface Antecedencia {
  antecedencia_reserva_horas: number;
  antecedencia_maxima_reserva_dias: number | null;
  antecedencia_cancelamento_horas: number;
}

export function ConfiguracaoAntecedencia({ filialId }: { filialId: string }) {
  const [valores, setValores] = useState<Antecedencia | null>(null);
  const [erro, setErro] = useState('');
  const [sucesso, setSucesso] = useState('');
  const [revisao, setRevisao] = useState(0);
  const [salvando, setSalvando] = useState(false);
  const enviando = useRef(false);
  const caminho = '/filiais/' + filialId + '/antecedencia';

  useEffect(() => {
    const controller = new AbortController();
    api.get<Antecedencia>(caminho, { signal: controller.signal })
      .then(({ data }) => { if (!controller.signal.aborted) { setValores(data); setErro(''); } })
      .catch(e => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Não foi possível carregar a antecedência.')); });
    return () => controller.abort();
  }, [caminho, revisao]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!valores || enviando.current) return;
    const marca = contextoAtual();
    enviando.current = true;
    setSalvando(true);
    setErro('');
    setSucesso('');
    try {
      const { data } = await api.put<Antecedencia>(caminho, valores);
      if (contextoValido(marca)) { setValores(data); setSucesso('Antecedência salva.'); }
    } catch (e: unknown) {
      if (contextoValido(marca)) setErro(mensagemErro(e, 'Não foi possível salvar a antecedência.'));
    } finally {
      enviando.current = false;
      setSalvando(false);
    }
  }

  return <section aria-labelledby="antecedencia-titulo">
    <h2 id="antecedencia-titulo">Antecedência da agenda</h2>
    {erro && <p role="alert">{erro}</p>}
    {!valores && !erro && <p role="status">Carregando antecedência…</p>}
    {!valores && erro && <button type="button" onClick={() => { setErro(''); setRevisao(n => n + 1); }}>Tentar novamente</button>}
    {valores && <form onSubmit={salvar}>
      <p>Regras para clientes no portal. Use zero nos prazos mínimos para desativá-los e deixe o máximo em branco para permitir reservas sem limite de dias.</p>
      <fieldset disabled={salvando}>
        <label>Antecedência mínima para agendar (horas)
          <input type="number" min={0} max={87600} step={1} required value={Number.isNaN(valores.antecedencia_reserva_horas) ? '' : valores.antecedencia_reserva_horas}
            onChange={e => setValores({ ...valores, antecedencia_reserva_horas: e.target.valueAsNumber })} />
        </label>
        <label>Antecedência máxima para agendar (dias)
          <input type="number" min={1} max={3650} step={1} value={valores.antecedencia_maxima_reserva_dias ?? ''}
            onChange={e => setValores({ ...valores, antecedencia_maxima_reserva_dias: e.target.value === '' ? null : e.target.valueAsNumber })} />
        </label>
        <label>Antecedência mínima para cancelar (horas)
          <input type="number" min={0} max={87600} step={1} required value={Number.isNaN(valores.antecedencia_cancelamento_horas) ? '' : valores.antecedencia_cancelamento_horas}
            onChange={e => setValores({ ...valores, antecedencia_cancelamento_horas: e.target.valueAsNumber })} />
        </label>
        <button type="submit">{salvando ? 'Salvando…' : 'Salvar antecedência'}</button>
      </fieldset>
    </form>}
    {sucesso && <p role="status">{sucesso}</p>}
  </section>;
}
