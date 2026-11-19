import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { useFilial } from '../../services/filialEstado';
import { useUsuario } from '../../services/usuario';
import { moeda } from '../../services/comandas';
import { erroFinanceiro } from '../../services/financeiro';
import '../estoque/Estoque.css';
import './Repasses.css';

type Pessoa = { id: string; nome: string };
type Parcela = { id: string; fechamento_id: string; congelado: string; pago: string; disponivel: string; ajuste_negativo: string };
type Fechamento = { id: string; inicio: string; fim: string; valor: string; registrado_em: string; registrado_por: string };
type Pagamento = { id: string; fechamento_id: string; valor: string; metodo: string; data_pagamento: string; estornado: string; registrado_por: string };
type Estorno = { id: string; pagamento_id: string; valor: string; motivo: string; registrado_em: string; registrado_por: string };
type Demonstrativo = { gerada: string; liberada: string; pendente: string; elegivel: string; deficit_pago: string; bloqueado: boolean; itens: { item_id: string; origem: string; descricao: string; tipo: string; gerada: string; liberada: string; elegivel: string }[]; parcelas: Parcela[]; fechamentos: Fechamento[]; pagamentos: Pagamento[]; estornos: Estorno[] };
type Pendente = { chave: string; caminho: string; dados: object; filial: string; profissional: string };

function mensal() {
  const partes = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Recife', year: 'numeric', month: '2-digit' }).formatToParts(new Date());
  const ano = Number(partes.find(p => p.type === 'year')!.value), mes = partes.find(p => p.type === 'month')!.value;
  const ultimoDia = new Date(Date.UTC(ano, Number(mes), 0)).getUTCDate();
  return { inicio: `${ano}-${mes}-01`, fim: `${ano}-${mes}-${String(ultimoDia).padStart(2, '0')}` };
}
function carregar(storage: string): Pendente | null {
  const raw = localStorage.getItem(storage); if (!raw) return null;
  const p = JSON.parse(raw) as Pendente;
  if (!p || !/^[0-9a-f-]{36}$/i.test(p.chave) || !/^\/repasses\/profissionais\/[0-9a-f-]{36}\/fechamentos(?:\/[0-9a-f-]{36}\/pagamentos(?:\/[0-9a-f-]{36}\/estornos)?)?$/i.test(p.caminho) || !p.dados || !p.filial || !p.profissional) throw new Error('Operação pendente inválida; preserve os dados e procure o administrador.');
  return p;
}

export function Repasses() {
  const usuario = useUsuario(), { filialId } = useFilial();
  const permitido = ['admin','recepcao'].includes(usuario.perfil), admin = usuario.perfil === 'admin';
  const [profissionais,setProfissionais] = useState<Pessoa[]>([]), [profissional,setProfissional] = useState('');
  const [periodo,setPeriodo] = useState(mensal), [resultado,setDados] = useState<Demonstrativo | null>(null);
  const [contextoDados,setContextoDados] = useState('');
  const contexto = `${filialId}:${profissional}:${periodo.inicio}:${periodo.fim}`;
  const dados = contextoDados === contexto ? resultado : null;
  const [erro,setErro] = useState(''), [ocupado,setOcupado] = useState(false), [revisao,setRevisao] = useState(0);
  const [fechamento,setFechamento] = useState(''), [pagamento,setPagamento] = useState(''), [valor,setValor] = useState('');
  const [metodo,setMetodo] = useState('pix'), [motivo,setMotivo] = useState('');
  const storage = `relaxabarber:repasse:${usuario.id}`;
  const [inicial] = useState(() => { try { return { pendente: carregar(storage), erro: '' }; } catch { return { pendente: null, erro: 'Operação pendente inválida; preserve os dados e procure o administrador.' }; } });
  const [pendente,setPendente] = useState<Pendente | null>(inicial.pendente);
  const trava = useRef(false);
  useEffect(() => {
    if (!filialId || !permitido) return;
    const controller = new AbortController();
    api.get<Pessoa[]>('/usuarios/barbeiros',{params:{filial_id:filialId},signal:controller.signal}).then(r => { if (!controller.signal.aborted) setProfissionais(r.data); }).catch(() => { if (!controller.signal.aborted) setErro('Não foi possível consultar profissionais.'); });
    return () => controller.abort();
  },[filialId,permitido]);
  useEffect(() => {
    if (!filialId || !profissional || !permitido) return;
    const controller=new AbortController();
    api.get<Demonstrativo>(`/repasses/profissionais/${profissional}`,{params:{filial_id:filialId,...periodo},signal:controller.signal}).then(r => { if (!controller.signal.aborted) { setDados(r.data);setContextoDados(`${filialId}:${profissional}:${periodo.inicio}:${periodo.fim}`);setErro(''); } }).catch(e => { if (!controller.signal.aborted) { setDados(null);setErro(erroFinanceiro(e)); } });
    return () => controller.abort();
  },[filialId,profissional,periodo,permitido,revisao]);
  if (!permitido) return <main><p>Consulta restrita à gestão.</p></main>;
  async function executar(op: Pendente, recuperar = false) {
    if (trava.current || ocupado || op.filial !== filialId || op.profissional !== profissional) return;
    trava.current = true;
    setOcupado(true);setErro('');
    try {
      const anterior=carregar(storage);if(anterior && JSON.stringify(anterior)!==JSON.stringify(op)) throw new Error('Recupere a operação pendente.');
      localStorage.setItem(storage,JSON.stringify(op));setPendente(op);
      await api.post(op.caminho,op.dados,{params:{filial_id:op.filial},headers:{'Idempotency-Key':op.chave}});
      localStorage.removeItem(storage);setPendente(null);setFechamento('');setPagamento('');setValor('');setMotivo('');setDados(null);setRevisao(n=>n+1);
    } catch(e) {
      const status=(e as {response?:{status?:number}})?.response?.status;
      const codigo=(e as {response?:{data?:{detail?:{codigo?:string}}}})?.response?.data?.detail?.codigo;
      if(!recuperar && status && status>=400 && status<500 && status!==408 && status!==429 && codigo!=='conflito_idempotencia'){localStorage.removeItem(storage);setPendente(null);}
      setErro(erroFinanceiro(e));
    } finally { trava.current = false; setOcupado(false); }
  }
  function enviar(caminho: string, corpo: object) {
    if (!filialId || !profissional || pendente || ocupado || inicial.erro) return;
    void executar({chave:crypto.randomUUID(),caminho,dados:corpo,filial:filialId,profissional});
  }
  const base=`/repasses/profissionais/${profissional}/fechamentos`;
  return <main className="repasse-pagina"><header><p>OPERAÇÃO / COMISSÕES</p><h1>Fechamento e repasse de comissões</h1><p>Registre somente repasses confirmados. Nenhuma transferência é executada pelo sistema.</p></header>
    {(erro || inicial.erro) && <p role="alert">{erro || inicial.erro}</p>}
    {pendente && <aside role="status"><p>Operação aguardando confirmação. Selecione a filial e o profissional originais e recupere-a antes de continuar.</p><button disabled={ocupado || filialId!==pendente.filial || profissional!==pendente.profissional} onClick={()=>void executar(pendente, true)}>Recuperar operação</button></aside>}
    <section className="repasse-painel"><div className="repasse-filtros"><label>Profissional<select value={profissional} onChange={e=>{setProfissional(e.target.value);setDados(null);setFechamento('');setPagamento('');}}><option value="">Selecione</option>{profissionais.map(p=><option value={p.id} key={p.id}>{p.nome}</option>)}</select></label>
      <label>Início<input type="date" value={periodo.inicio} onChange={e=>{setDados(null);setPeriodo({...periodo,inicio:e.target.value});}} /></label><label>Fim<input type="date" value={periodo.fim} onChange={e=>{setDados(null);setPeriodo({...periodo,fim:e.target.value});}} /></label><button onClick={()=>{setDados(null);setPeriodo(mensal());}}>Mês atual</button></div></section>
    {dados && <><section className="repasse-painel"><h2>Demonstrativo por data de origem</h2><div className="repasse-totais"><p>Gerada <strong>{moeda(dados.gerada)}</strong></p><p>Liberada <strong>{moeda(dados.liberada)}</strong></p><p>Aguardando recebimento <strong>{moeda(dados.pendente)}</strong></p><p>Disponível para fechamento <strong>{moeda(dados.elegivel)}</strong></p></div>
      {dados.bloqueado && <p role="alert">Há {moeda(dados.deficit_pago)} de repasses acima da comissão atualmente liberada. Novos fechamentos e pagamentos estão bloqueados até a conciliação.</p>}
      <table><thead><tr><th>Origem</th><th>Item</th><th>Gerada</th><th>Liberada</th><th>Elegível</th></tr></thead><tbody>{dados.itens.map(i=><tr key={i.item_id}><td>{i.origem}</td><td>{i.descricao} · {i.tipo}</td><td>{moeda(i.gerada)}</td><td>{moeda(i.liberada)}</td><td>{moeda(i.elegivel)}</td></tr>)}</tbody></table>
      {admin && <button disabled={ocupado || !!pendente || !!inicial.erro || dados.bloqueado || Number(dados.elegivel)<=0} onClick={()=>enviar(base,periodo)}>Fechar período</button>}</section>
      <section className="repasse-painel"><h2>Fechamentos e saldo</h2>{dados.fechamentos.map(f=>{const parcelas=dados.parcelas.filter(p=>p.fechamento_id===f.id);const disponivel=parcelas.reduce((n,p)=>n+Number(p.disponivel),0);return <article key={f.id}><h3>{f.inicio} a {f.fim}</h3><p>Congelado: {moeda(f.valor)} · Saldo disponível: {moeda(disponivel.toFixed(2))}</p><p>Pago: {moeda(parcelas.reduce((n,p)=>n+Number(p.pago),0).toFixed(2))} · Ajustes: {moeda(parcelas.reduce((n,p)=>n+Number(p.ajuste_negativo),0).toFixed(2))}</p><p>Registrado em {f.registrado_em} · Responsável: {f.registrado_por}</p>{admin && <button disabled={ocupado || !!pendente || dados.bloqueado || disponivel<=0} onClick={()=>{setFechamento(f.id);setPagamento('');setValor('');}}>Registrar repasse</button>}</article>})}</section>
      {admin && fechamento && !pagamento && <form className="repasse-painel" onSubmit={e=>{e.preventDefault();enviar(`${base}/${fechamento}/pagamentos`,{valor:valor.replace(',','.'),metodo,data_pagamento:new Date().toISOString()});}}><h2>Registrar repasse confirmado</h2><label>Valor (R$)<input required inputMode="decimal" value={valor} onChange={e=>setValor(e.target.value)} /></label><label>Método<select value={metodo} onChange={e=>setMetodo(e.target.value)}><option value="pix">Pix</option><option value="dinheiro">Dinheiro</option><option value="transferencia">Transferência</option></select></label><button disabled={ocupado || !!pendente}>Confirmar repasse</button><button type="button" onClick={()=>setFechamento('')}>Cancelar</button></form>}
      <section className="repasse-painel"><h2>Histórico de repasses e estornos</h2>{dados.pagamentos.map(p=><article key={p.id}><p>{p.data_pagamento} · {p.metodo} · {moeda(p.valor)} · Estornado: {moeda(p.estornado)} · Responsável: {p.registrado_por}</p>{admin && <button disabled={ocupado || !!pendente || Number(p.estornado)>=Number(p.valor)} onClick={()=>{setFechamento(p.fechamento_id);setPagamento(p.id);setValor('');setMotivo('');}}>Estornar repasse</button>}</article>)}{dados.estornos.map(e=><p key={e.id}>Estorno {moeda(e.valor)} · {e.motivo} · {e.registrado_em} · Responsável: {e.registrado_por}</p>)}</section>
      {admin && fechamento && pagamento && <form className="repasse-painel" onSubmit={e=>{e.preventDefault();enviar(`${base}/${fechamento}/pagamentos/${pagamento}/estornos`,{valor:valor.replace(',','.'),motivo});}}><h2>Estorno administrativo</h2><label>Valor (R$)<input required value={valor} onChange={e=>setValor(e.target.value)} /></label><label>Motivo<textarea required value={motivo} onChange={e=>setMotivo(e.target.value)} /></label><button disabled={ocupado || !!pendente}>Confirmar estorno</button><button type="button" onClick={()=>{setFechamento('');setPagamento('');}}>Cancelar</button></form>}
    </>}
  </main>;
}
