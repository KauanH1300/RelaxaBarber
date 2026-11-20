import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { useUsuario } from '../../services/usuario';
import { erroFinanceiro } from '../../services/financeiro';
import type { ResumoFinanceiro } from '../../services/financeiro';
import { moeda } from '../../services/comandas';
import type { Comanda } from '../../services/comandas';
import { confirmacaoProduto, enviar, lerPendente, versaoProdutoDesatualizada } from '../../services/operacaoProduto';
import type { Operacao } from '../../services/operacaoProduto';

type Produto = { id: string; nome: string; saldo: string; preco_venda: string | null; ativo: boolean; venda: boolean };
type Movimento = { item_id: string; acao: string; quantidade: number; saldo: string };

export function ProdutosAgendados({ comanda, bloqueado, aoBloqueio, aoAtualizar }: { comanda: Comanda; bloqueado: boolean; aoBloqueio: (valor: boolean) => void; aoAtualizar: () => void }) {
  const usuario = useUsuario();
  const gestor = ['admin', 'recepcao'].includes(usuario.perfil);
  const storage = `relaxabarber:agendada:produtos:${usuario.id}:${comanda.filial_id}:${comanda.id}`;
  const [inicial] = useState(() => { try { return { pendente: lerPendente(storage), erro: '' }; } catch { return { pendente: null, erro: 'Operação pendente inválida. Preserve os dados e procure o administrador.' }; } });
  const [pendente, setPendente] = useState<Operacao | null>(inicial.pendente);
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [historico, setHistorico] = useState<Movimento[]>([]);
  const [consulta, setConsulta] = useState<{ comanda: Comanda; financeiro: ResumoFinanceiro } | null>(null);
  const financeiro = consulta?.comanda === comanda ? consulta.financeiro : null;
  const [produto, setProduto] = useState('');
  const [quantidade, setQuantidade] = useState(1);
  const [profissionais, setProfissionais] = useState<{ id: string; nome: string }[]>([]);
  const [profissional, setProfissional] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [revisao, setRevisao] = useState(0);
  const [erro, setErro] = useState(inicial.erro);
  const [sucesso, setSucesso] = useState('');
  const trava = useRef(false);
  useEffect(() => { aoBloqueio(ocupado || !!pendente || !!inicial.erro); }, [ocupado, pendente, inicial.erro, aoBloqueio]);
  useEffect(() => {
    if (!gestor) return;
    const controller = new AbortController();
    Promise.all([
      api.get<Produto[]>('/estoque/produtos', { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
      api.get<ResumoFinanceiro>(`/comandas/${comanda.id}/financeiro`, { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
      api.get<Movimento[]>(`/comandas/${comanda.id}/produtos/historico`, { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
      api.get<{ id: string; nome: string }[]>('/usuarios/barbeiros', { params: { filial_id: comanda.filial_id }, signal: controller.signal }),
    ]).then(([estoque, resumo, movimentos, equipe]) => { if (!controller.signal.aborted) { setProdutos(estoque.data.filter(p => p.ativo && p.venda)); setConsulta({ comanda, financeiro: resumo.data }); setHistorico(movimentos.data); setProfissionais(equipe.data); } }).catch(() => { if (!controller.signal.aborted) { setConsulta(null); setErro('Não foi possível consultar produtos e financeiro.'); } });
    return () => controller.abort();
  }, [comanda, gestor, revisao]);
  if (!gestor) return null;
  const movimentado = !!financeiro && (financeiro.historico.pagamentos.length > 0 || financeiro.historico.estornos.length > 0);
  const travado = bloqueado || ocupado || !!pendente || !!inicial.erro || !financeiro || financeiro.situacao !== 'aberto' || comanda.status !== 'aberta' || comanda.atendimento.status === 'cancelado' || movimentado;
  async function executar(op: Operacao) {
    if (trava.current) return;
    trava.current = true; setOcupado(true); setErro(''); setSucesso('');
    try { await enviar(storage, comanda.filial_id, op); setPendente(null); setSucesso(confirmacaoProduto(op.metodo)); setConsulta(null); setRevisao(n => n + 1); aoAtualizar(); }
    catch (e) {
      try { setPendente(lerPendente(storage)); } catch { setErro('Operação pendente inválida. Procure o administrador.'); return; }
      setErro(erroFinanceiro(e));
      if (versaoProdutoDesatualizada(e)) { setConsulta(null); setRevisao(n => n + 1); aoAtualizar(); }
    }
    finally { trava.current = false; setOcupado(false); }
  }
  function nova(metodo: Operacao['metodo'], caminho: string, dados?: unknown) { if (!travado) void executar({ chave: crypto.randomUUID(), metodo, caminho, versao: comanda.versao_itens, ...(dados === undefined ? {} : { dados }) }); }
  return <section className="comanda-adicionar-servico avulsa-painel" aria-label="Produtos da comanda"><h4>Produtos</h4>
    {ocupado && <p role="status">Confirmando alteração de produto…</p>}{sucesso && <p role="status">{sucesso}</p>}
    {erro && <p role="alert">{erro}</p>}{movimentado && <p>Produtos bloqueados após pagamento. Estorno financeiro não devolve estoque.</p>}
    {pendente && <aside role="status"><p>Há uma operação aguardando confirmação.</p><button disabled={ocupado} onClick={() => void executar(pendente)}>Recuperar operação</button></aside>}
    <form onSubmit={e => { e.preventDefault(); nova('post', `/comandas/${comanda.id}/produtos`, { produto_id: produto, quantidade, profissional_id: profissional || null }); }}>
      <label>Produto<select required value={produto} disabled={travado} onChange={e => setProduto(e.target.value)}><option value="">Selecione</option>{produtos.map(p => <option key={p.id} value={p.id}>{p.nome} · disponível {p.saldo} · {p.preco_venda ? moeda(p.preco_venda) : 'sem preço'}</option>)}</select></label>
      <label>Quantidade<input type="number" min="1" max="999" required value={quantidade} disabled={travado} onChange={e => setQuantidade(Number(e.target.value))} /></label>
      <label>Profissional para comissão<select value={profissional} disabled={travado} onChange={e => setProfissional(e.target.value)}><option value="">Nenhum · sem comissão</option>{profissionais.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}</select></label>
      <button type="submit" disabled={travado || !produto}>Adicionar produto</button>
    </form>
    <ul>{comanda.itens.filter(i => i.tipo === 'produto' && i.ativo !== false && i.produto_id).map(i => <li key={i.id}>{i.descricao} · {i.quantidade} × {moeda(i.preco_unitario)} <button disabled={travado || i.quantidade <= 1} aria-label={`Diminuir ${i.descricao}`} onClick={() => nova('put', `/comandas/${comanda.id}/produtos/${i.id}`, { quantidade: i.quantidade - 1 })}>−</button><button disabled={travado || i.quantidade >= 999} aria-label={`Aumentar ${i.descricao}`} onClick={() => nova('put', `/comandas/${comanda.id}/produtos/${i.id}`, { quantidade: i.quantidade + 1 })}>+</button><button disabled={travado} onClick={() => nova('delete', `/comandas/${comanda.id}/produtos/${i.id}`)}>Remover</button></li>)}</ul>
    <details><summary>Histórico de produtos</summary><ol>{historico.map((h, i) => <li key={`${h.item_id}-${i}`}>{h.acao} · quantidade {h.quantidade} · saldo {h.saldo}</li>)}</ol></details>
  </section>;
}
