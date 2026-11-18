import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import api from '../../services/api';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { useUsuario } from '../../services/usuario';
import { useFilial } from '../../services/filialEstado';
import { csv, filtrar, indicadores, moeda, quantidade as formatarQuantidade, rotulos, situacao } from './estoqueUtils';
import type { Produto } from './estoqueUtils';
import './Estoque.css';

type Movimento = { id: string; tipo: string; quantidade: string; saldo_apos: string; motivo: string; registrado_por: string; registrado_em: string };
type Formulario = Omit<Produto, 'id' | 'saldo'>;
type Pendente = { id: string; chave: string; dados: { tipo: string; quantidade: string; motivo: string } };
const vazio = (): Formulario => ({ nome: '', unidade: 'un', venda: true, consumo: false, custo: '0', preco_venda: '0', estoque_minimo: '0', ativo: true });
const icone = (nome: string) => <span aria-hidden="true" className="material-symbols-outlined">{nome}</span>;
const tamanho = 8;

export function Estoque() {
  const usuario = useUsuario(); const { filialId } = useFilial();
  const storage = `relaxabarber:estoque:${usuario.id}:${filialId}`;
  const permitido = ['admin', 'recepcao'].includes(usuario.perfil); const admin = usuario.perfil === 'admin';
  const [produtos, setProdutos] = useState<Produto[]>([]); const [selecionado, setSelecionado] = useState<Produto | null>(null);
  const [historico, setHistorico] = useState<Movimento[]>([]); const [carregando, setCarregando] = useState(true);
  const [form, setForm] = useState<Formulario>(vazio); const [editando, setEditando] = useState<string | null>(null);
  const [modal, setModal] = useState<'produto' | 'movimento' | null>(null);
  const [tipo, setTipo] = useState<'entrada' | 'baixa' | 'ajuste'>('entrada');
  const [quantia, setQuantia] = useState(''); const [motivo, setMotivo] = useState('');
  const [erro, setErro] = useState(''); const [aviso, setAviso] = useState(''); const [ocupado, setOcupado] = useState(false);
  const [busca, setBusca] = useState(''); const [finalidade, setFinalidade] = useState('todos'); const [estado, setEstado] = useState('todos'); const [pagina, setPagina] = useState(1);
  const trava = useRef(false);
  const [recuperacao] = useState(() => { try { const texto = localStorage.getItem(storage); if (!texto) return { valor: null as Pendente | null, erro: false }; const valor = JSON.parse(texto) as Pendente; if (!valor.id || !valor.chave || !valor.dados?.tipo || !valor.dados?.quantidade || !valor.dados?.motivo) throw new Error(); return { valor, erro: false }; } catch { return { valor: null, erro: true }; } });
  const [pendente, setPendente] = useState<Pendente | null>(recuperacao.valor);
  const dados = useMemo(() => indicadores(produtos), [produtos]);
  const filtrados = useMemo(() => filtrar(produtos, busca, finalidade, estado), [produtos, busca, finalidade, estado]);
  const paginas = Math.max(1, Math.ceil(filtrados.length / tamanho)); const paginaAtual = Math.min(pagina, paginas); const visiveis = filtrados.slice((paginaAtual - 1) * tamanho, paginaAtual * tamanho);
  const bloqueado = ocupado || !!pendente || recuperacao.erro;
  async function carregar() { const r = await api.get<Produto[]>('/estoque/produtos'); setProdutos(r.data); return r.data; }
  async function carregarHistorico(id: string) { const r = await api.get<Movimento[]>(`/estoque/produtos/${id}/movimentos`); setHistorico(r.data); }
  useEffect(() => {
    if (!permitido) return;
    const controller = new AbortController();
    api.get<Produto[]>('/estoque/produtos', { signal: controller.signal }).then(r => {
      if (controller.signal.aborted) return;
      setProdutos(r.data); setCarregando(false);
      const item = r.data.find(p => p.id === recuperacao.valor?.id);
      if (item) { setSelecionado(item); setModal('movimento'); api.get<Movimento[]>(`/estoque/produtos/${item.id}/movimentos`, { signal: controller.signal }).then(h => { if (!controller.signal.aborted) setHistorico(h.data); }).catch(e => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Erro ao carregar histórico')); }); }
    }).catch(e => { if (!controller.signal.aborted) { setCarregando(false); setErro(mensagemErro(e, 'Não foi possível carregar o estoque')); } });
    return () => controller.abort();
  }, [permitido, recuperacao.valor]);
  useEffect(() => {
    if (!modal) return;
    const fechar = (e: KeyboardEvent) => { if (e.key === 'Escape' && !ocupado) setModal(null); };
    document.addEventListener('keydown', fechar);
    return () => document.removeEventListener('keydown', fechar);
  }, [modal, ocupado]);
  async function salvar(e: FormEvent) {
    e.preventDefault(); if (!admin || trava.current || bloqueado) return;
    trava.current = true; setOcupado(true); setErro(''); setAviso('');
    try { const payload = { ...form, preco_venda: form.venda ? form.preco_venda : null }; if (editando) await api.put(`/estoque/produtos/${editando}`, payload); else await api.post('/estoque/produtos', payload); setModal(null); setForm(vazio()); setEditando(null); await carregar(); setAviso('Item salvo com sucesso.'); }
    catch (e) { setErro(mensagemErro(e, 'Não foi possível salvar o item') + (escritaIncerta(e) ? ' Consulte a lista antes de repetir.' : '')); }
    finally { trava.current = false; setOcupado(false); }
  }
  async function enviarMovimento(p: Pendente) {
    if (trava.current || recuperacao.erro) return; trava.current = true; setOcupado(true); setErro(''); setAviso('');
    try { localStorage.setItem(storage, JSON.stringify(p)); setPendente(p); } catch { setErro('Não foi possível guardar a operação; nenhum movimento foi enviado.'); trava.current = false; setOcupado(false); return; }
    let confirmado = false;
    try {
      await api.post(`/estoque/produtos/${p.id}/movimentos`, p.dados, { headers: { 'Idempotency-Key': p.chave } }); confirmado = true;
      localStorage.removeItem(storage); setPendente(null); setQuantia(''); setMotivo('');
      const atual = await carregar(); setSelecionado(atual.find(x => x.id === p.id) ?? null); await carregarHistorico(p.id); setAviso('Movimentação registrada.');
    } catch (e) {
      if (!confirmado && !escritaIncerta(e)) { try { localStorage.removeItem(storage); setPendente(null); } catch { setErro('Não foi possível remover a operação pendente.'); return; } }
      setErro(confirmado ? 'Movimento confirmado, mas não foi possível atualizar os dados. Consulte o histórico.' : mensagemErro(e, 'Não foi possível movimentar o estoque') + (escritaIncerta(e) ? ' Recupere a operação antes de criar outra.' : ''));
    } finally { trava.current = false; setOcupado(false); }
  }
  function abrirProduto(p?: Produto) { setErro(''); setAviso(''); setEditando(p?.id ?? null); setForm(p ? { nome:p.nome, unidade:p.unidade, venda:p.venda, consumo:p.consumo, custo:p.custo, preco_venda:p.preco_venda, estoque_minimo:p.estoque_minimo, ativo:p.ativo } : vazio()); setModal('produto'); }
  function abrirMovimento(p: Produto) { setErro(''); setAviso(''); setSelecionado(p); setHistorico([]); setQuantia(''); setMotivo(''); setTipo('entrada'); setModal('movimento'); void carregarHistorico(p.id).catch(e => setErro(mensagemErro(e, 'Erro ao carregar histórico'))); }
  function exportar() { const url = URL.createObjectURL(new Blob([csv(produtos)], { type:'text/csv;charset=utf-8' })); const a = document.createElement('a'); a.href=url; a.download='estoque-filial.csv'; a.click(); URL.revokeObjectURL(url); }
  if (!permitido) return <p role="alert">Sem permissão para consultar estoque.</p>;
  return <section className="estoque" aria-labelledby="estoque-titulo">
    <header className="est-cabecalho"><div><p className="est-eyebrow">● OPERAÇÃO <span>/</span> INVENTÁRIO DA FILIAL</p><h1 id="estoque-titulo">Controle de Estoque &amp; Insumos</h1><p>Gestão de produtos para venda e insumos de uso interno da sua unidade.</p></div><div className="est-acoes-topo"><button type="button" className="est-secundario" onClick={exportar} disabled={carregando}>{icone('download')} Exportar inventário</button>{admin && <button type="button" className="est-dourado" onClick={() => abrirProduto()} disabled={bloqueado}>{icone('add')} Novo item</button>}</div></header>
    {erro && <p className="est-mensagem erro" role="alert">{erro}</p>}{aviso && <p className="est-mensagem" role="status">{aviso}</p>}{recuperacao.erro && <p className="est-mensagem erro" role="alert">Não foi possível recuperar a operação pendente. Preserve os dados e procure o administrador.</p>}
    {pendente && <aside className="est-pendente" role="status"><strong>Movimentação aguardando confirmação</strong><p>Recupere a operação original antes de registrar outra.</p><button className="est-secundario" disabled={ocupado} onClick={() => void enviarMovimento(pendente)}>Recuperar operação</button></aside>}
    <div className="est-indicadores" aria-label="Indicadores do estoque"><article><div><span>VALOR EM ESTOQUE</span>{icone('account_balance_wallet')}</div><strong>{moeda(dados.valor)}</strong><p>Custo dos itens ativos em estoque</p><i /></article><article><div><span>PONTO DE REPOSIÇÃO</span>{icone('warning')}</div><strong>{dados.baixo + dados.esgotado} {dados.baixo + dados.esgotado === 1 ? 'item' : 'itens'}</strong><p>{dados.esgotado} esgotado(s) · {dados.baixo} no mínimo</p><i className="alerta" /></article><article><div><span>ITENS ATIVOS</span>{icone('inventory_2')}</div><strong>{dados.ativos}</strong><p>De {dados.total} itens cadastrados</p><i /></article><article><div><span>FINALIDADES</span>{icone('category')}</div><strong>{dados.venda} / {dados.consumo}</strong><p>Para venda / uso interno</p><i className="verde" /></article></div>
    <div className="est-filtros"><div className="est-abas" role="group" aria-label="Finalidade dos itens">{([['todos','Todos os itens',dados.total,'apps'],['venda','Produtos para venda',dados.venda,'shopping_bag'],['consumo','Insumos de uso interno',dados.consumo,'content_cut']] as const).map(([v,n,c,i]) => <button key={v} type="button" aria-pressed={finalidade===v} className={finalidade===v?'ativa':''} onClick={() => {setFinalidade(v);setPagina(1);}}>{icone(i)} {n} <small>{c}</small></button>)}</div><div className="est-filtros-linha"><label className="est-busca">{icone('search')}<span className="est-sr">Buscar por nome</span><input placeholder="Buscar por nome..." value={busca} onChange={e => {setBusca(e.target.value);setPagina(1);}} /></label><label><span className="est-sr">Situação do estoque</span><select value={estado} onChange={e => {setEstado(e.target.value);setPagina(1);}}><option value="todos">Situação: Todas</option><option value="normal">Normal</option><option value="baixo">Estoque baixo</option><option value="esgotado">Esgotado</option><option value="inativo">Inativo</option></select></label><button type="button" className="est-limpar" onClick={() => {setBusca('');setEstado('todos');setFinalidade('todos');setPagina(1);}}>{icone('filter_alt_off')} Limpar filtros</button></div></div>
    <div className="est-tabela-caixa"><div className="est-tabela-scroll" tabIndex={0} role="region" aria-label="Tabela de itens do estoque"><table><thead><tr><th>PRODUTO / INSUMO</th><th>DESTINAÇÃO</th><th>QTD. ATUAL &amp; NÍVEL</th><th>CUSTO UNIT.</th><th>PREÇO DE VENDA</th><th>AÇÕES</th></tr></thead><tbody>{visiveis.map(p => { const s=situacao(p); return <tr key={p.id} className={s==='esgotado'?'est-linha-critica':''}><td><div className="est-item"><span className="est-item-icone">{icone(p.consumo && !p.venda ? 'content_cut' : 'inventory_2')}</span><div><strong>{p.nome}</strong><small>{p.ativo ? 'Ativo' : 'Inativo'} · {p.unidade}</small></div></div></td><td><div className="est-tags">{p.venda && <span className="est-tag venda">{icone('shopping_bag')} Venda</span>}{p.consumo && <span className="est-tag consumo">{icone('content_cut')} Uso interno</span>}</div></td><td><div className={`est-nivel ${s}`}><div><strong>{formatarQuantidade(p.saldo)} {p.unidade}</strong><span>{rotulos[s]}</span></div><div className="est-barra"><i style={{width: `${Math.min(100, Number(p.estoque_minimo) > 0 ? Number(p.saldo) / Number(p.estoque_minimo) * 50 : Number(p.saldo)>0 ? 100 : 0)}%`}} /></div><small>Mínimo: {formatarQuantidade(p.estoque_minimo)} {p.unidade}</small></div></td><td>{moeda(p.custo)}</td><td>{p.preco_venda === null ? '—' : moeda(p.preco_venda)}</td><td><div className="est-acoes-linha"><button type="button" onClick={() => abrirMovimento(p)} disabled={bloqueado} aria-label={`Movimentar e ver histórico de ${p.nome}`}>{icone('swap_vert')}<span>Movimentar</span></button>{admin && <button type="button" onClick={() => abrirProduto(p)} disabled={bloqueado} aria-label={`Editar ${p.nome}`}>{icone('edit')}<span>Editar</span></button>}</div></td></tr>; })}</tbody></table>{carregando ? <p className="est-vazio" role="status">Carregando estoque...</p> : !filtrados.length && <p className="est-vazio">Nenhum item encontrado para os filtros selecionados.</p>}</div><footer className="est-paginacao"><p>{filtrados.length ? `Mostrando ${(paginaAtual-1)*tamanho+1}–${Math.min(paginaAtual*tamanho,filtrados.length)} de ${filtrados.length} itens` : 'Nenhum item para exibir'}</p><div><button type="button" aria-label="Página anterior" disabled={paginaAtual<=1} onClick={() => setPagina(paginaAtual-1)}>‹</button><span>Página {paginaAtual} de {paginas}</span><button type="button" aria-label="Próxima página" disabled={paginaAtual>=paginas} onClick={() => setPagina(paginaAtual+1)}>›</button></div></footer></div>
    {!carregando && dados.baixo + dados.esgotado > 0 && <aside className="est-alerta"><div className="est-alerta-icone">{icone('inventory')}</div><div><strong>Reposição recomendada <small>{dados.baixo + dados.esgotado} {dados.baixo + dados.esgotado === 1 ? 'item' : 'itens'}</small></strong><p>Há itens esgotados ou com saldo no nível mínimo. Confira os itens da filial.</p></div><button type="button" onClick={() => {setEstado(dados.esgotado ? 'esgotado' : 'baixo');setFinalidade('todos');setPagina(1);}}>Ver itens</button></aside>}
    {modal && <div className="est-modal-fundo" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget && !ocupado) setModal(null); }}><section className="est-modal" role="dialog" aria-modal="true" aria-labelledby="est-modal-titulo"><header><div><p className="est-eyebrow">ESTOQUE DA FILIAL</p><h2 id="est-modal-titulo">{modal === 'produto' ? (editando ? 'Editar item' : 'Novo item') : 'Movimentação e histórico'}</h2></div><button type="button" className="est-fechar" aria-label="Fechar" disabled={ocupado} onClick={() => setModal(null)}>{icone('close')}</button></header>{erro && <p className="est-mensagem erro" role="alert">{erro}</p>}
      {modal === 'produto' ? <form className="est-form" onSubmit={salvar}><p>Cadastre produtos para venda, insumos de uso interno ou ambos.</p><label>Nome do item<input autoFocus required maxLength={150} value={form.nome} onChange={e => setForm({...form,nome:e.target.value})} /></label><div className="est-form-grade"><label>Unidade<input required maxLength={20} value={form.unidade} onChange={e => setForm({...form,unidade:e.target.value})} /></label><label>Estoque mínimo<input type="number" min="0" step="0.001" required value={form.estoque_minimo} onChange={e => setForm({...form,estoque_minimo:e.target.value})} /></label></div><fieldset><legend>Finalidade</legend><label className="est-check"><input type="checkbox" checked={form.venda} onChange={e => setForm({...form,venda:e.target.checked})} /> Produto para venda</label><label className="est-check"><input type="checkbox" checked={form.consumo} onChange={e => setForm({...form,consumo:e.target.checked})} /> Insumo de uso interno</label></fieldset><div className="est-form-grade"><label>Custo unitário (R$)<input type="number" min="0" step="0.01" required value={form.custo} onChange={e => setForm({...form,custo:e.target.value})} /></label>{form.venda && <label>Preço de venda (R$)<input type="number" min="0" step="0.01" required value={form.preco_venda ?? ''} onChange={e => setForm({...form,preco_venda:e.target.value})} /></label>}</div><label className="est-check"><input type="checkbox" checked={form.ativo} onChange={e => setForm({...form,ativo:e.target.checked})} /> Item ativo</label><footer><button type="button" className="est-secundario" disabled={ocupado} onClick={() => setModal(null)}>Cancelar</button><button className="est-dourado" disabled={bloqueado || (!form.venda && !form.consumo)}>Salvar item</button></footer></form> : selecionado && <div className="est-form"><p><strong>{selecionado.nome}</strong> · Saldo atual: {formatarQuantidade(selecionado.saldo)} {selecionado.unidade}</p>{pendente ? <p>Recupere a operação pendente antes de continuar.</p> : selecionado.ativo && <form className="est-form" onSubmit={e => { e.preventDefault(); void enviarMovimento({id:selecionado.id,chave:crypto.randomUUID(),dados:{tipo,quantidade:quantia,motivo}}); }}><div className="est-form-grade"><label>Movimento<select value={tipo} onChange={e => setTipo(e.target.value as typeof tipo)}><option value="entrada">Entrada</option><option value="baixa">Baixa para consumo</option><option value="ajuste">Ajuste positivo ou negativo</option></select></label><label>Quantidade<input required type="number" step="0.001" value={quantia} onChange={e => setQuantia(e.target.value)} /></label></div><label>Motivo<input required maxLength={1000} value={motivo} onChange={e => setMotivo(e.target.value)} /></label><footer><button className="est-dourado" disabled={bloqueado}>Registrar movimento</button></footer></form>}<h3>Histórico de movimentações</h3>{historico.length ? <ul className="est-historico">{historico.map(m => <li key={m.id}><strong>{m.tipo} · {formatarQuantidade(m.quantidade)} {selecionado.unidade}</strong><span>{new Date(m.registrado_em).toLocaleString('pt-BR')} · saldo {formatarQuantidade(m.saldo_apos)} · responsável {m.registrado_por}</span><p>{m.motivo}</p></li>)}</ul> : <p>Nenhuma movimentação registrada.</p>}</div>}
    </section></div>}
  </section>;
}
