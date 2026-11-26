import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { CabecalhoPublico, RodapePublico } from './ComponentesPublicos';
import { precoPublico } from './useCatalogoPublico';
import { guardarEscolhas, lerEscolhas, hojeLocal, confirmarReserva, consultarReserva, filiaisPublicas, servicosDaFilial } from '../../services/agendamentoPublico';
import type { FilialPublica } from '../../services/agendamentoPublico';
import type { Servico } from '../../services/servico';
import type { EscolhasAgendamento, ReservaConfirmada } from '../../services/agendamentoPublico';
import { perfilCliente } from '../../services/portalCliente';
import { mensagemErro } from '../../services/erros';
import { useAgendaPublica } from './useAgendaPublica';
import './publico.css';

const etapas = ['servico', 'barbeiro', 'horario', 'autenticacao', 'confirmacao'] as const;
const titulos = ['Escolha seu serviço', 'Com quem você prefere?', 'Qual é o melhor momento?', 'Entre para revisar', 'Revise suas preferências'];
const rotulos = ['Serviço', 'Barbeiro', 'Data e horário', 'Seu acesso', 'Confirmação'];

export function AgendamentoPublico() {
  const [params, setParams] = useSearchParams();
  const [escolhas, setEscolhas] = useState<EscolhasAgendamento>(() => lerEscolhas());
  const [filiais, setFiliais] = useState<FilialPublica[] | null>(null);
  const servicoInicial = useRef(params.get('servico'));
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [estado, setEstado] = useState<'carregando' | 'erro' | 'pronto'>('carregando');
  const [erro, setErro] = useState('');
  const [reserva, setReserva] = useState<ReservaConfirmada | null>(null);
  const [revisao, setRevisao] = useState(0);
  const [ocupado, setOcupado] = useState(false); const [incerto, setIncerto] = useState(false); const trava = useRef(false);
  const [sessao, setSessao] = useState<'carregando' | 'autenticado' | 'anonimo' | 'erro'>('carregando');
  useEffect(() => { const c = new AbortController(); filiaisPublicas(c.signal).then(rows => {
    if (c.signal.aborted) return; setFiliais(rows);
    if (rows.length === 1) setEscolhas(old => old.filial === rows[0].id ? old : { ...old, filial: rows[0].id, servicos: [], barbeiro: '', hora: '', chave: undefined });
  }).catch(() => { if (!c.signal.aborted) setErro('Não foi possível carregar as filiais.'); }); return () => c.abort(); }, []);
  useEffect(() => { if (!escolhas.filial) return; const c = new AbortController();
    servicosDaFilial(escolhas.filial, c.signal).then(rows => { if (!c.signal.aborted) {
      setServicos(rows); setEstado('pronto');
      const inicial = servicoInicial.current; servicoInicial.current = null;
      if (inicial && rows.some(s => s.id === inicial)) setEscolhas(old => old.servicos.length ? old : { ...old, servicos: [inicial] });
    } })
      .catch(() => { if (!c.signal.aborted) setEstado('erro'); }); return () => c.abort(); }, [escolhas.filial]);
  const selecionados = servicos.filter(s => escolhas.servicos.includes(s.id));
  const duracaoTotal = selecionados.reduce((total, s) => total + s.tempo_estimado, 0);
  const servico = selecionados.length === escolhas.servicos.length && selecionados.length > 0 && duracaoTotal <= 480 && selecionados.length <= 20;
  const { equipe, agenda } = useAgendaPublica(escolhas.filial, servico ? escolhas.servicos.join(',') : '', escolhas.barbeiro, escolhas.data, revisao);
  const profissionalValido = escolhas.barbeiro === 'qualquer' ? !!equipe?.itens.length : !!equipe?.itens.some(p => p.id === escolhas.barbeiro);
  const solicitado = etapas.indexOf(params.get('etapa') as typeof etapas[number]);
  const maximo = !servico ? 0 : !escolhas.barbeiro ? 1 : !escolhas.data || escolhas.data < hojeLocal() || !escolhas.hora ? 2 : 4;
  const etapa = Math.min(solicitado < 0 ? 0 : solicitado, maximo);
  useEffect(() => {
    if (etapa < 3) return;
    const controller = new AbortController();
    perfilCliente(controller.signal).then(() => { if (!controller.signal.aborted) setSessao('autenticado'); })
      .catch(falha => { if (!controller.signal.aborted) setSessao(axios.isAxiosError(falha) && falha.response?.status === 401 ? 'anonimo' : 'erro'); });
    return () => controller.abort();
  }, [etapa]);
  function alterar(campos: Partial<EscolhasAgendamento>) {
    if (campos.filial && campos.filial !== escolhas.filial) { setEstado('carregando'); setServicos([]); }
    const novas = { ...escolhas, ...campos, chave: undefined }; setEscolhas(novas); guardarEscolhas(novas); setErro('');
  }
  function navegar(indice: number) {
    if (!guardarEscolhas(escolhas)) { setErro('Não foi possível guardar suas escolhas neste navegador. Habilite o armazenamento da sessão antes de continuar.'); return; }
    setParams({ etapa: etapas[indice] }); setErro('');
  }
  async function reservar(verificar = false) {
    if (trava.current || reserva || (incerto && !verificar)) return;
    trava.current = true; setOcupado(true); setErro('');
    const pedido = { ...escolhas, chave: escolhas.chave || crypto.randomUUID() };
    try {
      if (!guardarEscolhas(pedido)) { setErro('Não foi possível guardar a identificação do pedido. Habilite o armazenamento antes de confirmar.'); return; }
      setEscolhas(pedido);
      const resultado = verificar ? await consultarReserva(pedido.chave) : await confirmarReserva(pedido);
      setReserva(resultado); setIncerto(false);
    } catch (e) {
      const status = axios.isAxiosError(e) ? e.response?.status : undefined;
      if (status === 409 || status === 422) {
        alterar({ hora: '' }); setRevisao(n => n + 1); setParams({ etapa: 'horario' });
      }
      if (status === 401) setSessao('anonimo');
      const duvida = status === undefined || status >= 500;
      setIncerto(duvida || (incerto && !(verificar && status === 404)));
      setErro(verificar && status === 404 ? 'Nenhuma reserva confirmada para este pedido. Você pode tentar confirmar novamente com a mesma identificação.' : mensagemErro(e, 'Não foi possível confirmar a reserva.') + (duvida ? ' Não repita a confirmação. Use Verificar confirmação para consultar o resultado.' : ''));
    } finally { trava.current = false; setOcupado(false); }
  }
  const precisaEntrar = etapa >= 3 && sessao !== 'autenticado';
  return <div className="publico publico-agendar"><CabecalhoPublico /><main className="publico-agenda-main"><Link to="/" className="publico-text-link">← Voltar à barbearia</Link>
    <Link className="publico-text-link" to={escolhas.filial ? `/?filial_id=${encodeURIComponent(escolhas.filial)}#vitrine` : '/#vitrine'}>Ver produtos da vitrine</Link>
    <p className="publico-selo">SEU TEMPO, DO SEU JEITO</p><h1>Seu próximo atendimento.</h1>
    <p className="publico-nota">Horários da barbearia em America/Recife · a vaga só é garantida após a confirmação.</p>
    <ol className="publico-etapas" aria-label="Etapas do agendamento">{etapas.map((e, i) => <li key={e}><button type="button" aria-current={i === etapa ? 'step' : undefined} disabled={i > maximo || ocupado || incerto || !!reserva} onClick={() => navegar(i)}><span>{i + 1}</span>{rotulos[i]}</button></li>)}</ol>
    <div className="publico-agenda-grid"><section className="publico-painel" aria-labelledby="titulo-etapa"><p className="publico-selo">ETAPA {etapa + 1} DE 5</p><h2 id="titulo-etapa">{titulos[etapa]}</h2>
      {erro && <p role="alert">{erro}</p>}
      {etapa === 0 && <>{!filiais && !erro && <p role="status">Carregando filiais…</p>}{filiais && !filiais.length && <p>Nenhuma filial está disponível para agendamento online.</p>}
        {filiais && filiais.length > 1 && <fieldset className="publico-opcoes"><legend>Escolha a filial</legend>{filiais.map(f => <label key={f.id}><input type="radio" name="filial" checked={escolhas.filial === f.id} onChange={() => alterar({ filial: f.id, servicos: [], barbeiro: '', hora: '' })} /><span><strong>{f.nome}</strong><small>{f.endereco}</small></span></label>)}</fieldset>}
        {filiais?.length === 1 && <p>{filiais[0].nome} · {filiais[0].endereco}</p>}
        {escolhas.filial && <>{estado === 'carregando' && <p role="status">Carregando catálogo…</p>}{estado === 'erro' && <p role="alert">Não foi possível carregar os serviços.</p>}{estado === 'pronto' && !servicos.length && <p>Nenhum serviço disponível nesta filial.</p>}
        <fieldset className="publico-opcoes"><legend>Escolha um ou mais serviços</legend>{servicos.map(s => <label key={s.id}><input type="checkbox" checked={escolhas.servicos.includes(s.id)} onChange={e => alterar({ servicos: e.target.checked ? [...escolhas.servicos, s.id] : escolhas.servicos.filter(id => id !== s.id), barbeiro: '', hora: '' })} /><span><strong>{s.nome}</strong><small>{s.tempo_estimado} min</small></span><b>{precoPublico(s.preco)}</b></label>)}</fieldset>{(duracaoTotal > 480 || selecionados.length > 20) && <p role="alert">Escolha até 20 serviços com duração total de até 8 horas.</p>}</>}</>}
      {etapa === 1 && <><p>Profissionais ativos e habilitados para o serviço escolhido.</p>{!equipe && <p role="status">Consultando profissionais…</p>}{equipe?.erro && <p role="alert">{equipe.erro}</p>}{equipe && !equipe.erro && !equipe.itens.length && <p>Nenhum profissional habilitado disponível para este serviço.</p>}<fieldset className="publico-opcoes"><legend className="publico-sr">Profissional</legend>{!!equipe?.itens.length && [{ id: 'qualquer', nome: 'Qualquer barbeiro disponível' }, ...equipe.itens].map(p => <label key={p.id}><input type="radio" name="barbeiro" checked={escolhas.barbeiro === p.id} onChange={() => alterar({ barbeiro: p.id, hora: '' })} /><span><strong>{p.nome}</strong><small>{p.id === 'qualquer' ? 'Atribuído com segurança na confirmação' : 'Habilitado para este serviço'}</small></span></label>)}</fieldset></>}
      {etapa === 2 && <><p>Escolha um horário livre para a duração completa do serviço.</p><div className="publico-datas"><label>Data desejada<input type="date" min={hojeLocal()} value={escolhas.data} onChange={e => alterar({ data: e.target.value, hora: '' })} /></label></div>{escolhas.data && !agenda && <p role="status">Consultando horários…</p>}{agenda?.erro && <p role="alert">{agenda.erro}</p>}{agenda && !agenda.erro && !agenda.horarios.length && <p>Nenhum horário disponível nesta data. Escolha outro dia ou profissional.</p>}{!!agenda?.recomendados.length && <p>Horários recomendados ajudam a aproveitar melhor a agenda. Todos os horários listados podem ser escolhidos.</p>}<fieldset className="publico-opcoes"><legend className="publico-sr">Horários disponíveis</legend>{agenda?.horarios.map(h => <label key={h}><input type="radio" name="horario" checked={escolhas.hora === h} onChange={() => alterar({ hora: h })} /><strong>{h}{agenda.recomendados.includes(h) ? ' · Recomendado' : ''}</strong></label>)}</fieldset></>}
      {etapa >= 3 && <>{sessao === 'carregando' && <p role="status">Verificando seu acesso de cliente…</p>}{sessao === 'erro' && <p role="alert">Não foi possível verificar sua sessão. Nenhuma reserva foi criada. Tente novamente mais tarde.</p>}
        {precisaEntrar && sessao === 'anonimo' && <><p>Suas escolhas estão guardadas nesta aba. Entre ou crie sua conta para retornar à revisão.</p><div className="publico-acoes"><Link className="publico-botao" to="/cliente/entrar?retorno=agendamento" onClick={e => { if (!guardarEscolhas(escolhas)) { e.preventDefault(); setErro('Habilite o armazenamento da sessão para preservar suas escolhas.'); } }}>Entrar para revisar</Link><Link className="publico-text-link" to="/cliente/cadastro?retorno=agendamento" onClick={e => { if (!guardarEscolhas(escolhas)) { e.preventDefault(); setErro('Habilite o armazenamento da sessão para preservar suas escolhas.'); } }}>Criar minha conta</Link></div></>}
        {sessao === 'autenticado' && <><p role="status">Você está conectado à sua conta de cliente.</p>{etapa === 3 ? <button className="publico-botao" onClick={() => navegar(4)}>Revisar preferências →</button> : reserva ? <div role="status"><h3>Agendamento confirmado!</h3><p>{reserva.servico} com {reserva.barbeiro.nome}, em {reserva.data.split('-').reverse().join('/')} às {reserva.hora_inicio.slice(0, 5)} (America/Recife).</p><p>Protocolo: {reserva.id}</p><p>Nenhuma cobrança foi realizada.</p></div> : <><p>A disponibilidade será validada novamente agora. Seu atendimento ficará vinculado à sua conta.</p><button className="publico-botao" disabled={ocupado || incerto || !profissionalValido} onClick={() => void reservar()}>{ocupado ? 'Aguarde…' : 'Confirmar agendamento'}</button>{incerto && <button className="publico-voltar" disabled={ocupado} onClick={() => void reservar(true)}>Verificar confirmação</button>}</>}</>}
      </>}
      <div className="publico-passo-acoes">{etapa > 0 && !reserva && <button className="publico-voltar" disabled={ocupado || incerto} onClick={() => navegar(etapa - 1)}>← Voltar</button>}{etapa < 3 && <button className="publico-botao" disabled={etapa === 0 ? !servico : etapa === 1 ? !profissionalValido : !escolhas.data || escolhas.data < hojeLocal() || !escolhas.hora || !agenda?.horarios.includes(escolhas.hora)} onClick={() => navegar(etapa + 1)}>Continuar →</button>}</div>
    </section><aside className="publico-resumo"><p className="publico-selo">SUAS ESCOLHAS</p><h2>Um momento só seu.</h2><dl><dt>Filial</dt><dd>{filiais?.find(f => f.id === escolhas.filial)?.nome || 'A escolher'}</dd><dt>Serviços</dt><dd>{selecionados.map(s => s.nome).join(', ') || 'A escolher'}</dd><dt>Profissional</dt><dd>{reserva?.barbeiro.nome || (escolhas.barbeiro === 'qualquer' ? 'Qualquer barbeiro disponível' : equipe?.itens.find(p => p.id === escolhas.barbeiro)?.nome || 'A escolher')}</dd><dt>Data e horário · America/Recife</dt><dd>{escolhas.data ? escolhas.data.split('-').reverse().join('/') : 'A escolher'}{escolhas.hora && ` às ${escolhas.hora}`}</dd>{servico && <><dt>Total do catálogo</dt><dd>{precoPublico(selecionados.reduce((n, s) => n + Number(s.preco), 0))} · {selecionados.reduce((n, s) => n + s.tempo_estimado, 0)} min</dd></>}</dl><p>{reserva ? 'Reserva confirmada. Guarde seu protocolo.' : 'Escolhas guardadas nesta aba por até duas horas. A vaga é garantida apenas na confirmação.'}</p></aside></div>
  </main><RodapePublico /></div>;
}
