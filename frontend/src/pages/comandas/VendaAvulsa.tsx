import { useEffect, useState } from 'react';
import api from '../../services/api';
import { mensagemErro } from '../../services/erros';
import { useFilial } from '../../services/filialEstado';
import { useUsuario } from '../../services/usuario';
import type { Comanda } from '../../services/comandas';
import { moeda } from '../../services/comandas';
import type { ResumoFinanceiro } from '../../services/financeiro';
import { erroFinanceiro } from '../../services/financeiro';
import { FinanceiroComanda } from './FinanceiroComanda';
import { BeneficiosComanda } from './BeneficiosComanda';
import { CancelarComanda } from './CancelarComanda';
import './VendaAvulsa.css';

type Produto = { id: string; nome: string; saldo: string; preco_venda: string | null; venda: boolean; ativo: boolean };
type HistoricoProduto = { item_id: string; produto_id: string; acao: string; quantidade: number; saldo: string; registrado_em?: string };
type Operacao = { chave: string; metodo: 'post' | 'put' | 'delete'; caminho: string; dados?: unknown };

function erroOperacao(erro: unknown, fallback: string): string {
  const codigo = (erro as { response?: { data?: { detail?: { codigo?: string } } } })?.response?.data?.detail?.codigo;
  return codigo ? erroFinanceiro(erro) : mensagemErro(erro, fallback);
}

function lerPendente(storage: string): Operacao | null {
  const raw = localStorage.getItem(storage);
  if (!raw) return null;
  const p = JSON.parse(raw) as Operacao;
  if (!p || !/^[0-9a-f-]{36}$/i.test(p.chave) || !['post', 'put', 'delete'].includes(p.metodo) || !/^\/comandas\/(avulsas|[0-9a-f-]{36}\/produtos(?:\/[0-9a-f-]{36})?)$/i.test(p.caminho)) throw new Error('Operação pendente inválida. Preserve os dados e procure o administrador.');
  return p;
}

async function enviar(storage: string, filial: string, operacao: Operacao) {
  const anterior = lerPendente(storage);
  if (anterior && JSON.stringify(anterior) !== JSON.stringify(operacao)) throw new Error('Recupere a operação pendente antes de iniciar outra.');
  localStorage.setItem(storage, JSON.stringify(operacao));
  try {
    const resposta = await api.request({ method: operacao.metodo, url: operacao.caminho, data: operacao.dados, params: { filial_id: filial }, headers: { 'Idempotency-Key': operacao.chave } });
    if (operacao.caminho === '/comandas/avulsas' && !resposta.data?.id) throw new Error('Resposta de abertura inválida; preserve a chave e recupere a operação.');
    if (JSON.stringify(lerPendente(storage)) === JSON.stringify(operacao)) localStorage.removeItem(storage);
    return resposta.data as { id?: string };
  } catch (erro) {
    const status = (erro as { response?: { status?: number } })?.response?.status;
    const codigo = (erro as { response?: { data?: { detail?: { codigo?: string } } } })?.response?.data?.detail?.codigo;
    if (status && status >= 400 && status < 500 && status !== 408 && status !== 429 && codigo !== 'conflito_idempotencia' && JSON.stringify(lerPendente(storage)) === JSON.stringify(operacao)) localStorage.removeItem(storage);
    throw erro;
  }
}

export function AbrirVendaAvulsa({ aoAbrir }: { aoAbrir: (id: string) => void }) {
  const { filialId } = useFilial(); const usuario = useUsuario();
  const [ocupado, setOcupado] = useState(false); const [erro, setErro] = useState('');
  if (!['admin', 'recepcao'].includes(usuario.perfil)) return null;
  async function abrir() {
    if (!filialId || ocupado) return;
    const storage = `relaxabarber:avulsa:abertura:${usuario.id}:${filialId}`;
    setOcupado(true); setErro('');
    try {
      const op = lerPendente(storage) ?? { chave: crypto.randomUUID(), metodo: 'post' as const, caminho: '/comandas/avulsas' };
      const r = await enviar(storage, filialId, op);
      if (!r.id) throw new Error('Resposta de abertura inválida. Consulte as comandas antes de tentar novamente.');
      aoAbrir(r.id);
    } catch (e) { setErro(erroOperacao(e, 'Não foi possível confirmar a abertura. Tente novamente para recuperar a operação.')); }
    finally { setOcupado(false); }
  }
  return <div><button type="button" className="comandas-botao-dourado" disabled={!filialId || ocupado} onClick={() => void abrir()}>Nova venda avulsa</button>{erro && <p role="alert">{erro}</p>}</div>;
}

export function VendaAvulsaDetalhe({ comanda, aoAtualizar }: { comanda: Comanda; aoAtualizar: () => void }) {
  const usuario = useUsuario();
  const [produtos, setProdutos] = useState<Produto[]>([]); const [resumo, setResumo] = useState<ResumoFinanceiro | null>(null);
  const [historico, setHistorico] = useState<HistoricoProduto[]>([]);
  const [produto, setProduto] = useState(''); const [quantidade, setQuantidade] = useState(1);
  const [profissional, setProfissional] = useState(''); const [profissionais, setProfissionais] = useState<{ id: string; nome: string }[]>([]);
  const [revisao, setRevisao] = useState(0); const [ocupado, setOcupado] = useState(false); const [erro, setErro] = useState('');
  const [financeiroBloqueado, setFinanceiroBloqueado] = useState(false); const [beneficioBloqueado, setBeneficioBloqueado] = useState(false); const [cancelamentoBloqueado, setCancelamentoBloqueado] = useState(false);
  const storage = `relaxabarber:avulsa:itens:${usuario.id}:${comanda.filial_id}:${comanda.id}`;
  const [recuperacao] = useState(() => { try { return { pendente: lerPendente(storage), erro: '' }; } catch { return { pendente: null, erro: 'Operação pendente inválida. Preserve os dados e procure o administrador.' }; } });
  const [pendente, setPendente] = useState<Operacao | null>(recuperacao.pendente);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api.get<Produto[]>('/estoque/produtos', { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
      api.get<ResumoFinanceiro>(`/comandas/${comanda.id}/financeiro`, { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
      api.get<HistoricoProduto[]>(`/comandas/${comanda.id}/produtos/historico`, { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
      api.get<{ id: string; nome: string }[]>('/usuarios/barbeiros', { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
    ]).then(([estoque, financeiro, operacoes, equipe]) => { if (!controller.signal.aborted) { setProdutos(estoque.data.filter(p => p.ativo && p.venda)); setResumo(financeiro.data); setHistorico(operacoes.data); setProfissionais(equipe.data); } })
      .catch((e: unknown) => { if (!controller.signal.aborted) { setResumo(null); setErro(mensagemErro(e, 'Não foi possível consultar estoque e financeiro.')); } });
    return () => controller.abort();
  }, [comanda.id, comanda.filial_id, revisao]);
  const historicoFinanceiro = !!resumo && (resumo.historico.pagamentos.length > 0 || resumo.historico.estornos.length > 0);
  const bloqueado = ocupado || !!pendente || !!recuperacao.erro || financeiroBloqueado || beneficioBloqueado || cancelamentoBloqueado || !resumo || resumo.situacao !== 'aberto' || comanda.status !== 'aberta' || historicoFinanceiro;
  const gestor = ['admin', 'recepcao'].includes(usuario.perfil);
  function atualizar() { setResumo(null); setRevisao(n => n + 1); aoAtualizar(); }
  async function executar(op: Operacao) {
    if (ocupado) return;
    setOcupado(true); setErro('');
    try { await enviar(storage, comanda.filial_id, op); setPendente(null); atualizar(); }
    catch (e) { try { setPendente(lerPendente(storage)); } catch { setErro('Operação pendente inválida. Procure o administrador.'); return; } setErro(erroOperacao(e, 'Operação não confirmada. Recupere a operação antes de continuar.')); }
    finally { setOcupado(false); }
  }
  function nova(metodo: Operacao['metodo'], caminho: string, dados?: unknown) {
    if (bloqueado || !gestor) return;
    void executar({ chave: crypto.randomUUID(), metodo, caminho, ...(dados === undefined ? {} : { dados }) });
  }
  return <div className="avulsa-detalhe"><section className="avulsa-painel"><h3>Venda avulsa · {comanda.filial.nome}</h3>
    <p>Estado: {comanda.status} · Total: <strong>{moeda(comanda.total)}</strong></p>
    {(erro || recuperacao.erro) && <p role="alert">{erro || recuperacao.erro}</p>}{historicoFinanceiro && <p>Itens bloqueados após pagamento. Estorno financeiro não devolve estoque.</p>}
    {pendente && <aside role="status"><p>Há uma operação aguardando confirmação. Recupere-a antes de continuar.</p><button disabled={ocupado} onClick={() => void executar(pendente)}>Recuperar operação</button></aside>}
    {gestor && <form onSubmit={e => { e.preventDefault(); nova('post', `/comandas/${comanda.id}/produtos`, { produto_id: produto, quantidade, profissional_id: profissional || null }); }}>
      <label>Produto<select required value={produto} disabled={bloqueado} onChange={e => setProduto(e.target.value)}><option value="">Selecione</option>{produtos.map(p => <option key={p.id} value={p.id}>{p.nome} · disponível {p.saldo} · {p.preco_venda ? moeda(p.preco_venda) : 'sem preço'}</option>)}</select></label>
      <label>Quantidade<input type="number" min="1" max="999" required value={quantidade} disabled={bloqueado} onChange={e => setQuantidade(Number(e.target.value))} /></label>
      <label>Profissional para comissão<select value={profissional} disabled={bloqueado} onChange={e => setProfissional(e.target.value)}><option value="">Nenhum · sem comissão</option>{profissionais.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}</select></label>
      <button type="submit" disabled={bloqueado || !produto}>Adicionar produto</button></form>}
    <ul>{comanda.itens.map(item => <li key={item.id}><strong>{item.descricao}</strong> · {item.quantidade} × {moeda(item.preco_unitario)} = {moeda(item.subtotal)} {gestor && <span className="avulsa-acoes"><button disabled={bloqueado || item.quantidade <= 1} onClick={() => nova('put', `/comandas/${comanda.id}/produtos/${item.id}`, { quantidade: item.quantidade - 1 })} aria-label={`Diminuir ${item.descricao}`}>−</button><button disabled={bloqueado || item.quantidade >= 999} onClick={() => nova('put', `/comandas/${comanda.id}/produtos/${item.id}`, { quantidade: item.quantidade + 1 })} aria-label={`Aumentar ${item.descricao}`}>+</button><button disabled={bloqueado} onClick={() => nova('delete', `/comandas/${comanda.id}/produtos/${item.id}`)}>Remover</button></span>}</li>)}</ul>
    <details><summary>Histórico de produtos</summary>{historico.length ? <ol>{historico.map((h, i) => <li key={`${h.item_id}-${i}`}>{h.registrado_em ?? 'Registrado'} · {h.acao} · quantidade {h.quantidade} · saldo {h.saldo}</li>)}</ol> : <p>Nenhuma alteração registrada.</p>}</details>
    <BeneficiosComanda comanda={comanda} bloqueado={ocupado || !!pendente || !!recuperacao.erro || financeiroBloqueado || cancelamentoBloqueado} aoBloqueio={setBeneficioBloqueado} aoAtualizar={atualizar} />
    <CancelarComanda comanda={comanda} bloqueado={ocupado || !!pendente || !!recuperacao.erro || financeiroBloqueado || beneficioBloqueado || historicoFinanceiro || !resumo} aoBloqueio={setCancelamentoBloqueado} aoAtualizar={atualizar} />
    </section><FinanceiroComanda comanda={comanda} bloqueioExterno={ocupado || !!pendente || !!recuperacao.erro || beneficioBloqueado || cancelamentoBloqueado} aoBloqueio={setFinanceiroBloqueado} aoConfirmar={atualizar} />
  </div>;
}
