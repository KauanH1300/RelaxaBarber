import { MarcaEstabelecimento } from '../../components/MarcaEstabelecimento';
import { useEffect, useRef, useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { meusAgendamentos, meuAgendamento, opcoesRemarcacao, cancelarMeuAgendamento, remarcarMeuAgendamento } from '../../services/minhaAgenda';
import type { MeuAgendamento, OpcoesRemarcacao } from '../../services/minhaAgenda';
import { hojeLocal } from '../../services/agendamentoPublico';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import './portal.css';
import './minhaAgenda.css';

const nomes: Record<string, string> = { pendente: 'Pendente', aguardando: 'Aguardando', em_atendimento: 'Em atendimento', concluido: 'Concluído', cancelado: 'Cancelado', nao_compareceu: 'Não compareceu' };
const dinheiro = (v: string) => Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

export function CartaoAgendamento({ a, children }: { a: MeuAgendamento; children?: React.ReactNode }) {
  return <article className="portal-cartao agenda-cartao"><h3>{a.servicos.map(s => s.nome).join(' + ') || 'Serviço registrado'}</h3><span className="agenda-situacao">{nomes[a.status] || 'Situação indisponível'}</span>
    <dl><dt>Barbeiro</dt><dd>{a.barbeiro.nome}</dd><dt>Data e horário</dt><dd>{a.data.split('-').reverse().join('/')} · {a.hora_inicio.slice(0, 5)} — {a.hora_fim.slice(0, 5)}</dd><dt>Duração e valor reservado</dt><dd>{a.duracao} min · {dinheiro(a.valor)}</dd><dt>Barbearia</dt><dd>{a.filial}</dd></dl>{children}</article>;
}

function AlterarAgendamento({ a, atualizar }: { a: MeuAgendamento; atualizar: (novo: MeuAgendamento) => void }) {
  const navigate = useNavigate();
  const [modo, setModo] = useState<'cancelar' | 'remarcar' | null>(null);
  const [data, setData] = useState(''); const [hora, setHora] = useState(''); const [barbeiro, setBarbeiro] = useState('qualquer');
  const [opcoes, setOpcoes] = useState<{ chave: string; dados?: OpcoesRemarcacao; erro?: string } | null>(null);
  const [erro, setErro] = useState(''); const [ocupado, setOcupado] = useState(false); const [incerto, setIncerto] = useState(false);
  const [versao, setVersao] = useState(0); const trava = useRef(false); const montado = useRef(true);
  const chave = `${data}:${barbeiro}:${versao}`;
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => {
    if (modo !== 'remarcar') return;
    const controller = new AbortController();
    opcoesRemarcacao(a.id, data, barbeiro, controller.signal).then(dados => { if (!controller.signal.aborted) setOpcoes({ chave, dados }); })
      .catch(e => { if (!controller.signal.aborted) setOpcoes({ chave, erro: mensagemErro(e, 'Não foi possível consultar os horários.') }); });
    return () => controller.abort();
  }, [a.id, modo, data, barbeiro, chave]);
  const atuais = opcoes?.chave === chave ? opcoes : null;
  async function executar(consultar = false) {
    if (trava.current || (incerto && !consultar)) return;
    trava.current = true; setOcupado(true); setErro('');
    try {
      const resultado = consultar ? await meuAgendamento(a.id) : modo === 'cancelar' ? await cancelarMeuAgendamento(a) : await remarcarMeuAgendamento(a, data, hora, barbeiro);
      if (!montado.current) return;
      atualizar(resultado); setModo(null); setIncerto(false); setHora('');
    } catch (e) {
      if (!montado.current) return;
      const status = axios.isAxiosError(e) ? e.response?.status : undefined;
      if (status === 401) { navigate('/cliente/entrar?retorno=meus-agendamentos', { replace: true }); return; }
      setIncerto(incerto || escritaIncerta(e));
      setErro(mensagemErro(e, 'Não foi possível concluir a operação.') + (escritaIncerta(e) ? ' Resultado não confirmado. Consulte o agendamento antes de continuar.' : ''));
      if (status === 409 || status === 422) { setHora(''); setVersao(n => n + 1); setIncerto(true); }
    } finally { trava.current = false; if (montado.current) setOcupado(false); }
  }
  return <div className="agenda-operacoes">{erro && <p role="alert">{erro}</p>}
    {!modo && <>{a.pode_cancelar && <button onClick={() => setModo('cancelar')}>Cancelar agendamento</button>}{a.pode_remarcar && <button onClick={() => setModo('remarcar')}>Remarcar</button>}{!a.pode_cancelar && !a.pode_remarcar && a.proximo && <p>Para alterações, procure a recepção.</p>}</>}
    {modo === 'cancelar' && <p>Confirma o cancelamento deste agendamento? O histórico será preservado.</p>}
    {modo === 'remarcar' && <><p>Escolha uma nova data, horário ou profissional. O valor e os serviços serão mantidos.</p><label>Profissional<select disabled={ocupado || incerto} value={barbeiro} onChange={e => { setBarbeiro(e.target.value); setHora(''); }}><option value="qualquer">Qualquer barbeiro disponível</option>{atuais?.dados?.barbeiros.map(p => <option value={p.id} key={p.id}>{p.nome}</option>)}</select></label>
      <label>Nova data<input type="date" min={hojeLocal()} disabled={ocupado || incerto} value={data} onChange={e => { setData(e.target.value); setHora(''); }} /></label>
      {!atuais && <p role="status">Consultando opções…</p>}{atuais?.erro && <p role="alert">{atuais.erro}</p>}
      {data && atuais?.dados && !atuais.dados.horarios.length && <p>Nenhum horário livre. Escolha outro dia ou profissional.</p>}
      <fieldset disabled={ocupado || incerto}><legend>Horários disponíveis · America/Recife</legend><div className="agenda-horarios">{atuais?.dados?.horarios.map(h => <label key={h}><input type="radio" name={`horario-${a.id}`} checked={hora === h} onChange={() => setHora(h)} />{h}</label>)}</div></fieldset>
      {hora && <p>Confirmar remarcação para {data.split('-').reverse().join('/')} às {hora}? A disponibilidade será revalidada.</p>}</>}
    {modo && <>{incerto ? <button disabled={ocupado} onClick={() => void executar(true)}>Consultar agendamento atual</button> : <button disabled={ocupado || (modo === 'remarcar' && (!data || !hora || !atuais?.dados?.horarios.includes(hora)))} onClick={() => void executar()}>{ocupado ? 'Aguarde…' : modo === 'cancelar' ? 'Confirmar cancelamento' : 'Confirmar remarcação'}</button>}
      <button disabled={ocupado || incerto} onClick={() => { setModo(null); setErro(''); }}>Voltar</button></>}
  </div>;
}

export function MeusAgendamentos() {
  const [itens, setItens] = useState<MeuAgendamento[] | null>(null); const [erro, setErro] = useState('');
  const [semSessao, setSemSessao] = useState(false); const [versao, setVersao] = useState(0); const [mensagem, setMensagem] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    meusAgendamentos(controller.signal).then(dados => { if (!controller.signal.aborted) { setItens(dados); setErro(''); } })
      .catch(e => { if (!controller.signal.aborted) { if (axios.isAxiosError(e) && e.response?.status === 401) setSemSessao(true); else setErro(mensagemErro(e, 'Não foi possível carregar seus agendamentos.')); } });
    return () => controller.abort();
  }, [versao]);
  if (semSessao) return <Navigate to="/cliente/entrar?retorno=meus-agendamentos" replace />;
  function atualizar(novo: MeuAgendamento) { setItens(rows => rows?.map(a => a.id === novo.id ? novo : a) ?? null); setMensagem('Dados do agendamento atualizados. Confira a situação abaixo.'); }
  return <main className="portal-cliente minha-agenda"><header><Link to="/cliente"><MarcaEstabelecimento /></Link><nav aria-label="Portal do cliente"><Link to="/cliente/conta">Minha conta</Link><Link to="/agendar">Agendar horário</Link></nav></header>
    <div className="minha-agenda-main"><p className="portal-sobrancelha">Seu tempo, seus cuidados</p><h1>Meus Agendamentos</h1><p>Horários em America/Recife. Os valores são os registrados na reserva e não indicam quitação.</p>
      {mensagem && <p role="status">{mensagem}</p>}{erro && <><p role="alert">{erro}</p><button onClick={() => { setErro(''); setItens(null); setVersao(n => n + 1); }}>Consultar novamente</button></>}{!itens && !erro && <p role="status">Carregando seus agendamentos…</p>}
      {itens && [true, false].map(proximo => { const lista = itens.filter(a => a.proximo === proximo).sort((a, b) => (proximo ? 1 : -1) * (a.data + a.hora_inicio).localeCompare(b.data + b.hora_inicio)); return <section key={String(proximo)} aria-labelledby={proximo ? 'agenda-proximos' : 'agenda-historico'}><h2 id={proximo ? 'agenda-proximos' : 'agenda-historico'}>{proximo ? 'Próximos agendamentos' : 'Histórico de agendamentos'}</h2>{!lista.length && <p>{proximo ? 'Você não possui próximos agendamentos.' : 'Seu histórico de agendamentos está vazio.'}</p>}<div className="agenda-lista">{lista.map(a => <CartaoAgendamento key={a.id} a={a}><AlterarAgendamento key={`${a.id}:${a.atualizado_em}`} a={a} atualizar={atualizar} /></CartaoAgendamento>)}</div></section>; })}
    </div></main>;
}
