import { useEffect, useState, useRef } from 'react';
import type { FormEvent } from 'react';
import api from '../../services/api';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { useUsuario } from '../../services/usuario';
import { useFilial } from '../../services/filialEstado';
import '../servicos/servicos.css';

type Produto = { id: string; nome: string; unidade: string; venda: boolean; consumo: boolean; custo: string; preco_venda: string | null; estoque_minimo: string; saldo: string; ativo: boolean };
type Movimento = { id: string; tipo: string; quantidade: string; saldo_apos: string; motivo: string; registrado_por: string; registrado_em: string };
type Formulario = Omit<Produto, 'id' | 'saldo'>;
const vazio = (): Formulario => ({ nome: '', unidade: 'un', venda: true, consumo: false, custo: '0', preco_venda: '0', estoque_minimo: '0', ativo: true });
export function Estoque() {
  const usuario = useUsuario();
  const { filialId } = useFilial();
  const storage = `relaxabarber:estoque:${usuario.id}:${filialId}`;
  const permitido = ['admin', 'recepcao'].includes(usuario.perfil);
  const admin = usuario.perfil === 'admin';
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [selecionado, setSelecionado] = useState<Produto | null>(null);
  const [historico, setHistorico] = useState<Movimento[]>([]);
  const [form, setForm] = useState<Formulario>(vazio);
  const [editando, setEditando] = useState<string | null>(null);
  const [tipo, setTipo] = useState<'entrada' | 'baixa' | 'ajuste'>('entrada');
  const [quantidade, setQuantidade] = useState('');
  const [motivo, setMotivo] = useState('');
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const trava = useRef(false);
  type Pendente = { id: string; chave: string; dados: { tipo: string; quantidade: string; motivo: string } };
  const [recuperacao] = useState(() => { try { const texto = localStorage.getItem(storage); if (!texto) return { valor: null as Pendente | null, erro: false }; const valor = JSON.parse(texto) as Pendente; if (!valor.id || !valor.chave || !valor.dados?.tipo || !valor.dados?.quantidade || !valor.dados?.motivo) throw new Error(); return { valor, erro: false }; } catch { return { valor: null, erro: true }; } });
  const [pendente, setPendente] = useState<Pendente | null>(recuperacao.valor);
  async function carregar() { const r = await api.get<Produto[]>('/estoque/produtos'); setProdutos(r.data); return r.data; }
  async function carregarHistorico(id: string) { const r = await api.get<Movimento[]>(`/estoque/produtos/${id}/movimentos`); setHistorico(r.data); }
  useEffect(() => {
    if (!permitido) return;
    const controller = new AbortController();
    api.get<Produto[]>('/estoque/produtos', { signal: controller.signal }).then(r => {
      if (controller.signal.aborted) return;
      setProdutos(r.data);
      const item = r.data.find(p => p.id === recuperacao.valor?.id);
      if (item) {
        setSelecionado(item);
        api.get<Movimento[]>(`/estoque/produtos/${item.id}/movimentos`, { signal: controller.signal }).then(h => { if (!controller.signal.aborted) setHistorico(h.data); }).catch(e => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Erro ao carregar histórico')); });
      }
    }).catch(e => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Não foi possível carregar o estoque')); });
    return () => controller.abort();
  }, [permitido, recuperacao.valor]);
  async function salvar(e: FormEvent) {
    e.preventDefault(); if (!admin || trava.current) return;
    trava.current = true; setOcupado(true); setErro('');
    try {
      const dados = { ...form, preco_venda: form.venda ? form.preco_venda : null };
      if (editando) await api.put(`/estoque/produtos/${editando}`, dados); else await api.post('/estoque/produtos', dados);
      setForm(vazio()); setEditando(null); await carregar();
    } catch (e) { setErro(mensagemErro(e, 'Não foi possível salvar o produto') + (escritaIncerta(e) ? ' Consulte a lista antes de repetir.' : '')); }
    finally { trava.current = false; setOcupado(false); }
  }
  async function enviarMovimento(p: NonNullable<typeof pendente>) {
    if (trava.current || recuperacao.erro) return; trava.current = true; setOcupado(true); setErro('');
    try { localStorage.setItem(storage, JSON.stringify(p)); setPendente(p); } catch { setErro('Não foi possível guardar a operação; nenhum movimento foi enviado.'); trava.current = false; setOcupado(false); return; }
    try {
      await api.post(`/estoque/produtos/${p.id}/movimentos`, p.dados, { headers: { 'Idempotency-Key': p.chave } });
      localStorage.removeItem(storage); setPendente(null); setQuantidade(''); setMotivo('');
      const atual = await carregar(); setSelecionado(atual.find(x => x.id === p.id) ?? null); await carregarHistorico(p.id);
    } catch (e) { if (!escritaIncerta(e)) { try { localStorage.removeItem(storage); setPendente(null); } catch { setErro('Não foi possível remover a operação pendente.'); return; } } setErro(mensagemErro(e, 'Não foi possível movimentar o estoque') + (escritaIncerta(e) ? ' Recupere a operação antes de criar outra.' : '')); }
    finally { trava.current = false; setOcupado(false); }
  }
  if (!permitido) return <p role="alert">Sem permissão para consultar estoque.</p>;
  return <section className="servicos-container"><h1>Estoque manual</h1>{erro && <p role="alert">{erro}</p>}{recuperacao.erro && <p role="alert">Não foi possível recuperar a operação pendente. Preserve os dados e procure o administrador.</p>}
    {admin && <form onSubmit={salvar}><h2>{editando ? 'Editar produto ou insumo' : 'Cadastrar produto ou insumo'}</h2>
      <label>Nome <input required maxLength={150} value={form.nome} onChange={e => setForm({ ...form, nome: e.target.value })} /></label>{' '}
      <label>Unidade <input required maxLength={20} value={form.unidade} onChange={e => setForm({ ...form, unidade: e.target.value })} /></label>{' '}
      <label><input type="checkbox" checked={form.venda} onChange={e => setForm({ ...form, venda: e.target.checked })} /> Venda</label>{' '}
      <label><input type="checkbox" checked={form.consumo} onChange={e => setForm({ ...form, consumo: e.target.checked })} /> Consumo interno</label>{' '}
      <label>Custo <input type="number" min="0" step="0.01" required value={form.custo} onChange={e => setForm({ ...form, custo: e.target.value })} /></label>{' '}
      {form.venda && <label>Preço de venda <input type="number" min="0" step="0.01" required value={form.preco_venda ?? ''} onChange={e => setForm({ ...form, preco_venda: e.target.value })} /></label>}{' '}
      <label>Estoque mínimo <input type="number" min="0" step="0.001" required value={form.estoque_minimo} onChange={e => setForm({ ...form, estoque_minimo: e.target.value })} /></label>{' '}
      <label><input type="checkbox" checked={form.ativo} onChange={e => setForm({ ...form, ativo: e.target.checked })} /> Ativo</label>{' '}
      <button disabled={ocupado || !!pendente || recuperacao.erro}>Salvar</button>{editando && <button type="button" onClick={() => { setEditando(null); setForm(vazio()); }}>Cancelar edição</button>}
    </form>}
    <h2>Produtos e insumos da filial</h2><table className="servicos-tabela"><thead><tr><th>Nome</th><th>Finalidade</th><th>Saldo</th><th>Mínimo</th><th>Custo</th><th>Venda</th><th>Ações</th></tr></thead><tbody>
      {produtos.map(p => <tr key={p.id}><td>{p.nome}{!p.ativo && ' (inativo)'}</td><td>{[p.venda && 'Venda', p.consumo && 'Consumo'].filter(Boolean).join(' e ')}</td><td>{p.saldo} {p.unidade}{Number(p.saldo) <= Number(p.estoque_minimo) && ' · estoque mínimo'}</td><td>{p.estoque_minimo}</td><td>{p.custo}</td><td>{p.preco_venda ?? '—'}</td><td><button disabled={ocupado || !!pendente || recuperacao.erro} onClick={() => { setSelecionado(p); setHistorico([]); void carregarHistorico(p.id).catch(e => setErro(mensagemErro(e, 'Erro ao carregar histórico'))); }}>Movimentar e histórico</button>{admin && <button disabled={ocupado || !!pendente || recuperacao.erro} onClick={() => { setEditando(p.id); setForm({ nome:p.nome, unidade:p.unidade, venda:p.venda, consumo:p.consumo, custo:p.custo, preco_venda:p.preco_venda, estoque_minimo:p.estoque_minimo, ativo:p.ativo }); }}>Editar</button>}</td></tr>)}
    </tbody></table>
    {selecionado && <section><h2>{selecionado.nome} · saldo {selecionado.saldo} {selecionado.unidade}</h2>
      {pendente ? <div role="status"><p>Operação aguardando confirmação. Recupere-a antes de movimentar novamente.</p><button disabled={ocupado} onClick={() => void enviarMovimento(pendente)}>Recuperar operação</button></div> : selecionado.ativo && <form onSubmit={e => { e.preventDefault(); void enviarMovimento({ id: selecionado.id, chave: crypto.randomUUID(), dados: { tipo, quantidade, motivo } }); }}>
        <label>Movimento <select value={tipo} onChange={e => setTipo(e.target.value as typeof tipo)}><option value="entrada">Entrada</option><option value="baixa">Baixa para consumo</option><option value="ajuste">Ajuste (positivo ou negativo)</option></select></label>{' '}
        <label>Quantidade <input type="number" step="0.001" required value={quantidade} onChange={e => setQuantidade(e.target.value)} /></label>{' '}
        <label>Motivo <input required maxLength={1000} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>{' '}
        <button disabled={ocupado}>Registrar movimento</button></form>}
      <h3>Histórico</h3><ul>{historico.map(m => <li key={m.id}>{new Date(m.registrado_em).toLocaleString('pt-BR')} · {m.tipo} · {m.quantidade} · saldo {m.saldo_apos} · {m.motivo} · responsável {m.registrado_por}</li>)}</ul>
    </section>}
  </section>;
}
