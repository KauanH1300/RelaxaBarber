import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { CabecalhoPublico, RodapePublico } from './ComponentesPublicos';
import { useCatalogoPublico, precoPublico } from './useCatalogoPublico';
import { guardarEscolhas, lerEscolhas, preferencias, hojeLocal } from '../../services/agendamentoPublico';
import type { EscolhasAgendamento } from '../../services/agendamentoPublico';
import { perfilCliente } from '../../services/portalCliente';
import './publico.css';

const etapas = ['servico', 'barbeiro', 'horario', 'autenticacao', 'confirmacao'] as const;
const titulos = ['Escolha seu serviço', 'Com quem você prefere?', 'Qual é o melhor momento?', 'Entre para revisar', 'Revise suas preferências'];
const rotulos = ['Serviço', 'Barbeiro', 'Data e horário', 'Seu acesso', 'Confirmação'];

export function AgendamentoPublico() {
  const [params, setParams] = useSearchParams();
  const [escolhas, setEscolhas] = useState<EscolhasAgendamento>(() => ({ ...lerEscolhas(), ...(params.get('servico') ? { servico: params.get('servico')!.slice(0, 100) } : {}) }));
  const [erro, setErro] = useState('');
  const [sessao, setSessao] = useState<'carregando' | 'autenticado' | 'anonimo' | 'erro'>('carregando');
  const { servicos, estado } = useCatalogoPublico();
  const servico = servicos.find(s => s.id === escolhas.servico);
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
    const novas = { ...escolhas, ...campos }; setEscolhas(novas); guardarEscolhas(novas); setErro('');
  }
  function navegar(indice: number) {
    if (!guardarEscolhas(escolhas)) { setErro('Não foi possível guardar suas escolhas neste navegador. Habilite o armazenamento da sessão antes de continuar.'); return; }
    setParams({ etapa: etapas[indice] }); setErro('');
  }
  const precisaEntrar = etapa >= 3 && sessao !== 'autenticado';
  return <div className="publico publico-agendar"><CabecalhoPublico /><main className="publico-agenda-main"><Link to="/" className="publico-text-link">← Voltar à barbearia</Link>
    <p className="publico-selo">SEU TEMPO, DO SEU JEITO</p><h1>Seu próximo atendimento.</h1>
    <p className="publico-nota">Prévia do agendamento · suas escolhas ainda não reservam um horário.</p>
    <ol className="publico-etapas" aria-label="Etapas do agendamento">{etapas.map((e, i) => <li key={e}><button type="button" aria-current={i === etapa ? 'step' : undefined} disabled={i > maximo} onClick={() => navegar(i)}><span>{i + 1}</span>{rotulos[i]}</button></li>)}</ol>
    <div className="publico-agenda-grid"><section className="publico-painel" aria-labelledby="titulo-etapa"><p className="publico-selo">ETAPA {etapa + 1} DE 5</p><h2 id="titulo-etapa">{titulos[etapa]}</h2>
      {erro && <p role="alert">{erro}</p>}
      {etapa === 0 && <>{estado === 'carregando' && <p role="status">Carregando catálogo…</p>}{estado === 'erro' && <p role="alert">Não foi possível carregar os serviços. Reabra esta página quando a conexão estiver disponível.</p>}{estado === 'pronto' && !servicos.length && <p>Nenhum serviço disponível para escolha no momento.</p>}
        <fieldset className="publico-opcoes"><legend className="publico-sr">Serviços do catálogo</legend>{servicos.map(s => <label key={s.id}><input type="radio" name="servico" checked={escolhas.servico === s.id} onChange={() => alterar({ servico: s.id })} /><span><strong>{s.nome}</strong><small>{s.tempo_estimado} min</small></span><b>{precoPublico(s.preco)}</b></label>)}</fieldset></>}
      {etapa === 1 && <><p>Escolha uma preferência. A equipe disponível para cada serviço ainda depende de integração.</p><fieldset className="publico-opcoes"><legend className="publico-sr">Preferência de profissional</legend>{preferencias.map(p => <label key={p}><input type="radio" name="barbeiro" checked={escolhas.barbeiro === p} onChange={() => alterar({ barbeiro: p })} /><span><strong>{p}</strong><small>{p === 'Sem preferência' ? 'Escolher depois, conforme a disponibilidade' : 'Preferência visual · disponibilidade não confirmada'}</small></span></label>)}</fieldset></>}
      {etapa === 2 && <><p>Informe quando gostaria de ser atendido. A consulta de horários livres ainda não está integrada.</p><div className="publico-datas"><label>Data desejada<input type="date" min={hojeLocal()} value={escolhas.data} onChange={e => alterar({ data: e.target.value })} /></label><label>Horário desejado<input type="time" value={escolhas.hora} onChange={e => alterar({ hora: e.target.value })} /></label></div><p className="publico-nota">Esta escolha não confirma expediente, jornada do profissional ou disponibilidade.</p></>}
      {etapa >= 3 && <>{sessao === 'carregando' && <p role="status">Verificando seu acesso de cliente…</p>}{sessao === 'erro' && <p role="alert">Não foi possível verificar sua sessão. Nenhuma reserva foi criada. Tente novamente mais tarde.</p>}
        {precisaEntrar && sessao === 'anonimo' && <><p>Suas escolhas estão guardadas nesta aba. Entre ou crie sua conta para retornar à revisão.</p><div className="publico-acoes"><Link className="publico-botao" to="/cliente/entrar?retorno=agendamento" onClick={e => { if (!guardarEscolhas(escolhas)) { e.preventDefault(); setErro('Habilite o armazenamento da sessão para preservar suas escolhas.'); } }}>Entrar para revisar</Link><Link className="publico-text-link" to="/cliente/cadastro?retorno=agendamento" onClick={e => { if (!guardarEscolhas(escolhas)) { e.preventDefault(); setErro('Habilite o armazenamento da sessão para preservar suas escolhas.'); } }}>Criar minha conta</Link></div></>}
        {sessao === 'autenticado' && <><p role="status">Você está conectado à sua conta de cliente.</p>{etapa === 3 ? <button className="publico-botao" onClick={() => navegar(4)}>Revisar preferências →</button> : <><p>As preferências foram mantidas. A confirmação de reservas estará disponível após a integração da agenda pública.</p><button className="publico-botao" disabled>Reserva online em breve</button><p className="publico-nota">Nenhuma reserva foi criada. Não há cobrança nem confirmação de atendimento.</p></>}</>}
      </>}
      <div className="publico-passo-acoes">{etapa > 0 && <button className="publico-voltar" onClick={() => navegar(etapa - 1)}>← Voltar</button>}{etapa < 3 && <button className="publico-botao" disabled={etapa === 0 ? !servico : etapa === 1 ? !escolhas.barbeiro : !escolhas.data || escolhas.data < hojeLocal() || !escolhas.hora} onClick={() => navegar(etapa + 1)}>Continuar →</button>}</div>
    </section><aside className="publico-resumo"><p className="publico-selo">SUAS ESCOLHAS</p><h2>Um momento só seu.</h2><dl><dt>Serviço</dt><dd>{servico?.nome || 'A escolher'}</dd><dt>Profissional preferido</dt><dd>{escolhas.barbeiro || 'A escolher'}</dd><dt>Data e horário desejados</dt><dd>{escolhas.data ? escolhas.data.split('-').reverse().join('/') : 'A escolher'}{escolhas.hora && ` às ${escolhas.hora}`}</dd>{servico && <><dt>Valor do catálogo</dt><dd>{precoPublico(servico.preco)} · {servico.tempo_estimado} min</dd></>}</dl><p>Preferências guardadas nesta aba por até duas horas. Sem reserva de vaga.</p></aside></div>
  </main><RodapePublico /></div>;
}
