import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { useFilial } from '../../services/filialEstado';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { DIAS_SEMANA, type DiaHorario } from '../../services/horarios';
import { escritaIncerta, mensagemErro } from '../../services/erros';

interface Dia extends DiaHorario { intervalos: DiaHorario[] }
interface Excecao extends Dia { data: string }
interface Config { dias: Dia[]; excecoes: Excecao[] }
const folga = (dia_semana: number): Dia => ({ dia_semana, fechado: true, hora_inicio: null, hora_fim: null, intervalos: [] });

function EditorDia({ dia, alterar }: { dia: Dia; alterar: (d: Dia) => void }) {
  return <div>
    <label><input type="checkbox" checked={dia.fechado} onChange={e => alterar(e.target.checked ? folga(dia.dia_semana) : { ...dia, fechado: false, hora_inicio: '08:00', hora_fim: '18:00' })} />Folga</label>
    {!dia.fechado && <>
      <label>Início<input required type="time" value={dia.hora_inicio ?? ''} onChange={e => alterar({ ...dia, hora_inicio: e.target.value })} /></label>
      <label>Fim<input required type="time" value={dia.hora_fim ?? ''} onChange={e => alterar({ ...dia, hora_fim: e.target.value })} /></label>
      {dia.intervalos.map((i, n) => <div key={n}>
        <label>Início do intervalo<input required type="time" value={i.hora_inicio ?? ''} onChange={e => alterar({ ...dia, intervalos: dia.intervalos.map((v, k) => k === n ? { ...v, hora_inicio: e.target.value } : v) })} /></label>
        <label>Fim do intervalo<input required type="time" value={i.hora_fim ?? ''} onChange={e => alterar({ ...dia, intervalos: dia.intervalos.map((v, k) => k === n ? { ...v, hora_fim: e.target.value } : v) })} /></label>
        <button type="button" onClick={() => alterar({ ...dia, intervalos: dia.intervalos.filter((_, k) => k !== n) })}>Remover intervalo</button>
      </div>)}
      <button type="button" onClick={() => alterar({ ...dia, intervalos: [...dia.intervalos, { dia_semana: dia.dia_semana, fechado: false, hora_inicio: '12:00', hora_fim: '13:00' }] })}>Adicionar intervalo</button>
    </>}
  </div>;
}

export function Jornada({ barbeiroId }: { barbeiroId: string }) {
  const { filialId } = useFilial();
  // Remonta o formulário e descarta respostas/rascunhos ao trocar de filial.
  return filialId ? <FormularioJornada key={`${filialId}:${barbeiroId}`} filialId={filialId} barbeiroId={barbeiroId} /> : <p>Selecione uma filial.</p>;
}

function FormularioJornada({ filialId, barbeiroId }: { filialId: string; barbeiroId: string }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState(''); const [mensagem, setMensagem] = useState('');
  const [incerto, setIncerto] = useState(false); const [versao, setVersao] = useState(0);
  const [data, setData] = useState(''); const trava = useRef(false);
  const url = `/filiais/${encodeURIComponent(filialId)}/barbeiros/${encodeURIComponent(barbeiroId)}/jornada`;
  useEffect(() => {
    const controller = new AbortController(); const contexto = contextoAtual();
    api.get(url, { signal: controller.signal }).then(({ data: resposta }) => {
      if (!controller.signal.aborted && contextoValido(contexto)) {
        setConfig(resposta.configurado ? resposta : { dias: DIAS_SEMANA.map((_, d) => folga(d)), excecoes: [] });
        setIncerto(false); setErro('');
      }
    }).catch(e => { if (!controller.signal.aborted && contextoValido(contexto)) setErro(mensagemErro(e, 'Não foi possível consultar a jornada. Verifique o vínculo ativo nesta filial.')); });
    return () => controller.abort();
  }, [url, versao]);
  async function salvar(e: React.FormEvent) {
    e.preventDefault(); if (trava.current || !config || incerto) return;
    const contexto = contextoAtual();
    if (contexto.filialId !== filialId || !contexto.token) return;
    trava.current = true; setOcupado(true); setErro(''); setMensagem('');
    try {
      await api.put(url, { dias: config.dias, excecoes: config.excecoes });
      if (contextoValido(contexto)) setMensagem('Jornada salva com sucesso.');
    } catch (falha) {
      if (contextoValido(contexto)) { setErro(mensagemErro(falha, 'Não foi possível salvar. Revise horários, intervalos e reservas futuras.')); setIncerto(escritaIncerta(falha)); }
    } finally { trava.current = false; setOcupado(false); }
  }
  return <section aria-label="Jornada do barbeiro"><h3>Jornada na filial selecionada</h3>
    <p>Sem configuração, vale o expediente da filial. Exceções substituem o dia inteiro. Intervalos devem estar em ordem. Reservas futuras incompatíveis impedem o salvamento.</p>
    {erro && <p role="alert">{erro}</p>}{mensagem && <p role="status">{mensagem}</p>}
    {incerto && <p role="alert">Resultado não confirmado. Consulte novamente antes de salvar.</p>}
    <button type="button" disabled={ocupado} onClick={() => { setConfig(null); setMensagem(''); setVersao(n => n + 1); }}>Consultar novamente</button>
    {!config ? <p role="status">Aguardando consulta da jornada.</p> : <form onSubmit={e => void salvar(e)}><fieldset disabled={ocupado || incerto}>
      <legend>Semana de trabalho</legend>
      {config.dias.map((d, n) => <fieldset key={d.dia_semana}><legend>{DIAS_SEMANA[d.dia_semana]}</legend><EditorDia dia={d} alterar={dia => setConfig({ ...config, dias: config.dias.map((v, k) => k === n ? dia : v) })} /></fieldset>)}
      <h4>Exceções por data</h4>
      {config.excecoes.map((d, n) => <fieldset key={d.data}><legend>{d.data}</legend><EditorDia dia={d} alterar={dia => setConfig({ ...config, excecoes: config.excecoes.map((v, k) => k === n ? { ...dia, data: d.data } : v) })} /><button type="button" onClick={() => setConfig({ ...config, excecoes: config.excecoes.filter((_, k) => k !== n) })}>Remover exceção</button></fieldset>)}
      <label>Data da exceção<input type="date" value={data} onChange={e => setData(e.target.value)} /></label>
      <button type="button" disabled={!data || config.excecoes.some(e => e.data === data)} onClick={() => { const dia = (new Date(`${data}T12:00:00`).getDay() + 6) % 7; setConfig({ ...config, excecoes: [...config.excecoes, { ...folga(dia), data }] }); setData(''); }}>Adicionar exceção</button>
      <button type="submit">{ocupado ? 'Salvando…' : 'Salvar jornada'}</button>
    </fieldset></form>}
  </section>;
}
