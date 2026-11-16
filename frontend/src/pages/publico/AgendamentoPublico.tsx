import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { CabecalhoPublico, RodapePublico } from './ComponentesPublicos';
import { useCatalogoPublico, precoPublico } from './useCatalogoPublico';
import { guardarEscolhas, lerEscolhas, hojeLocal, confirmarReserva, consultarReserva } from '../../services/agendamentoPublico';
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
  const [escolhas, setEscolhas] = useState<EscolhasAgendamento>(() => ({ ...lerEscolhas(), ...(params.get('servico') ? { servico: params.get('servico')!.slice(0, 100) } : {}) }));
  const [erro, setErro] = useState('');
  const [reserva, setReserva] = useState<ReservaConfirmada | null>(null);
  const [revisao, setRevisao] = useState(0);
  const [ocupado, setOcupado] = useState(false); const [incerto, setIncerto] = useState(false); const trava = useRef(false);
  const [sessao, setSessao] = useState<'carregando' | 'autenticado' | 'anonimo' | 'erro'>('carregando');
  const { servicos, estado } = useCatalogoPublico();
  const servico = servicos.find(s => s.id === escolhas.servico);
  const { equipe, agenda } = useAgendaPublica(servico?.id || '', escolhas.barbeiro, escolhas.data, revisao);
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
    <p className="publico-selo">SEU TEMPO, DO SEU JEITO</p><h1>Seu próximo atendimento.</h1>
    <p className="publico-nota">Horários da barbearia em America/Recife · a vaga só é garantida após a confirmação.</p>
    <ol className="publico-etapas" aria-label="Etapas do agendamento">{etapas.map((e, i) => <li key={e}><button type="button" aria-current={i === etapa ? 'step' : undefined} disabled={i > maximo || ocupado || incerto || !!reserva} onClick={() => navegar(i)}><span>{i + 1}</span>{rotulos[i]}</button></li>)}</ol>
    <div className="publico-agenda-grid"><section className="publico-painel" aria-labelledby="titulo-etapa"><p className="publico-selo">ETAPA {etapa + 1} DE 5</p><h2 id="titulo-etapa">{titulos[etapa]}</h2>
      {erro && <p role="alert">{erro}</p>}
      {etapa === 0 && <>{estado === 'carregando' && <p role="status">Carregando catálogo…</p>}{estado === 'erro' && <p role="alert">Não foi possível carregar os serviços. Reabra esta página quando a conexão estiver disponível.</p>}{estado === 'pronto' && !servicos.length && <p>Nenhum serviço disponível para escolha no momento.</p>}
        <fieldset className="publico-opcoes"><legend className="publico-sr">Serviços do catálogo</legend>{servicos.map(s => <label key={s.id}><input type="radio" name="servico" checked={escolhas.servico === s.id} onChange={() => alterar({ servico: s.id, barbeiro: '', hora: '' })} /><span><strong>{s.nome}</strong><small>{s.tempo_estimado} min</small></span><b>{precoPublico(s.preco)}</b></label>)}</fieldset></>}
      {etapa === 1 && <><p>Profissionais ativos e habilitados para o serviço escolhido.</p>{!equipe && <p role="status">Consultando profissionais…</p>}{equipe?.erro && <p role="alert">{equipe.erro}</p>}{equipe && !equipe.erro && !equipe.itens.length && <p>Nenhum profissional habilitado disponível para este serviço.</p>}<fieldset className="publico-opcoes"><legend className="publico-sr">Profissional</legend>{!!equipe?.itens.length && [{ id: 'qualquer', nome: 'Qualquer barbeiro disponível' }, ...equipe.itens].map(p => <label key={p.id}><input type="radio" name="barbeiro" checked={escolhas.barbeiro === p.id} onChange={() => alterar({ barbeiro: p.id, hora: '' })} /><span><strong>{p.nome}</strong><small>{p.id === 'qualquer' ? 'Atribuído com segurança na confirmação' : 'Habilitado para este serviço'}</small></span></label>)}</fieldset></>}
      {etapa === 2 && <><p>Escolha um horário livre para a duração completa do serviço.</p><div className="publico-datas"><label>Data desejada<input type="date" min={hojeLocal()} value={escolhas.data} onChange={e => alterar({ data: e.target.value, hora: '' })} /></label></div>{escolhas.data && !agenda && <p role="status">Consultando horários…</p>}{agenda?.erro && <p role="alert">{agenda.erro}</p>}{agenda && !agenda.erro && !agenda.horarios.length && <p>Nenhum horário disponível nesta data. Escolha outro dia ou profissional.</p>}<fieldset className="publico-opcoes"><legend className="publico-sr">Horários disponíveis</legend>{agenda?.horarios.map(h => <label key={h}><input type="radio" name="horario" checked={escolhas.hora === h} onChange={() => alterar({ hora: h })} /><strong>{h}</strong></label>)}</fieldset></>}
      {etapa >= 3 && <>{sessao === 'carregando' && <p role="status">Verificando seu acesso de cliente…</p>}{sessao === 'erro' && <p role="alert">Não foi possível verificar sua sessão. Nenhuma reserva foi criada. Tente novamente mais tarde.</p>}
        {precisaEntrar && sessao === 'anonimo' && <><p>Suas escolhas estão guardadas nesta aba. Entre ou crie sua conta para retornar à revisão.</p><div className="publico-acoes"><Link className="publico-botao" to="/cliente/entrar?retorno=agendamento" onClick={e => { if (!guardarEscolhas(escolhas)) { e.preventDefault(); setErro('Habilite o armazenamento da sessão para preservar suas escolhas.'); } }}>Entrar para revisar</Link><Link className="publico-text-link" to="/cliente/cadastro?retorno=agendamento" onClick={e => { if (!guardarEscolhas(escolhas)) { e.preventDefault(); setErro('Habilite o armazenamento da sessão para preservar suas escolhas.'); } }}>Criar minha conta</Link></div></>}
        {sessao === 'autenticado' && <><p role="status">Você está conectado à sua conta de cliente.</p>{etapa === 3 ? <button className="publico-botao" onClick={() => navegar(4)}>Revisar preferências →</button> : reserva ? <div role="status"><h3>Agendamento confirmado!</h3><p>{reserva.servico} com {reserva.barbeiro.nome}, em {reserva.data.split('-').reverse().join('/')} às {reserva.hora_inicio.slice(0, 5)} (America/Recife).</p><p>Protocolo: {reserva.id}</p><p>Nenhuma cobrança foi realizada.</p></div> : <><p>A disponibilidade será validada novamente agora. Seu atendimento ficará vinculado à sua conta.</p><button className="publico-botao" disabled={ocupado || incerto || !profissionalValido} onClick={() => void reservar()}>{ocupado ? 'Aguarde…' : 'Confirmar agendamento'}</button>{incerto && <button className="publico-voltar" disabled={ocupado} onClick={() => void reservar(true)}>Verificar confirmação</button>}</>}</>}
      </>}
      <div className="publico-passo-acoes">{etapa > 0 && !reserva && <button className="publico-voltar" disabled={ocupado || incerto} onClick={() => navegar(etapa - 1)}>← Voltar</button>}{etapa < 3 && <button className="publico-botao" disabled={etapa === 0 ? !servico : etapa === 1 ? !profissionalValido : !escolhas.data || escolhas.data < hojeLocal() || !escolhas.hora || !agenda?.horarios.includes(escolhas.hora)} onClick={() => navegar(etapa + 1)}>Continuar →</button>}</div>
    </section><aside className="publico-resumo"><p className="publico-selo">SUAS ESCOLHAS</p><h2>Um momento só seu.</h2><dl><dt>Serviço</dt><dd>{servico?.nome || 'A escolher'}</dd><dt>Profissional</dt><dd>{reserva?.barbeiro.nome || (escolhas.barbeiro === 'qualquer' ? 'Qualquer barbeiro disponível' : equipe?.itens.find(p => p.id === escolhas.barbeiro)?.nome || 'A escolher')}</dd><dt>Data e horário · America/Recife</dt><dd>{escolhas.data ? escolhas.data.split('-').reverse().join('/') : 'A escolher'}{escolhas.hora && ` às ${escolhas.hora}`}</dd>{servico && <><dt>Valor do catálogo</dt><dd>{precoPublico(servico.preco)} · {servico.tempo_estimado} min</dd></>}</dl><p>{reserva ? 'Reserva confirmada. Guarde seu protocolo.' : 'Escolhas guardadas nesta aba por até duas horas. A vaga é garantida apenas na confirmação.'}</p></aside></div>
  </main><RodapePublico /></div>;
}
