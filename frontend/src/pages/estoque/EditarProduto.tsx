import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import api from '../../services/api';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { useFilial } from '../../services/filialEstado';
import { useUsuario } from '../../services/usuario';
import { quantidade, rotulos, situacao } from './estoqueUtils';
import type { Produto } from './estoqueUtils';
import './EditarProduto.css';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { ClassificacaoProduto } from './ClassificacaoProduto';
import { useConferencia } from '../../services/useConferencia';

type Movimento = { id: string; tipo: string; quantidade: string; saldo_apos: string; motivo: string; registrado_por: string; registrado_em: string };
type Formulario = Omit<Produto, 'id' | 'saldo' | 'foto_url'>;
function formulario(p: Produto): Formulario {
  return { nome:p.nome, unidade:p.unidade, venda:p.venda, consumo:p.consumo, categoria_id:p.categoria_id ?? null, marca_id:p.marca_id ?? null, custo:p.custo, preco_venda:p.preco_venda, comissao_padrao:p.comissao_padrao ?? '0', estoque_minimo:p.estoque_minimo, ativo:p.ativo, descricao_vitrine:p.descricao_vitrine ?? '', visivel_vitrine:p.visivel_vitrine ?? false };
}
function normalizar(f: Formulario) {
  return { ...f, nome: f.nome.trim(), unidade: f.unidade.trim(), descricao_vitrine: f.descricao_vitrine?.trim() || null,
    visivel_vitrine: f.venda && !f.consumo && !!f.visivel_vitrine, preco_venda: f.venda ? Number(f.preco_venda) : null,
    custo: Number(f.custo), comissao_padrao: Number(f.comissao_padrao), estoque_minimo: Number(f.estoque_minimo) };
}
const icon = (nome: string) => <span className="material-symbols-outlined" aria-hidden="true">{nome}</span>;

export function EditarProduto() {
  const { id } = useParams();
  const { filialId } = useFilial();
  const usuario = useUsuario();
  if (usuario.perfil !== 'admin') return <p role="alert">Sem permissão para editar produtos. <Link to="/estoque">Voltar ao estoque</Link></p>;
  if (!id || !filialId) return <p role="status">Selecione uma filial para editar o item.</p>;
  let pendente: boolean;
  try { pendente = !!localStorage.getItem(`relaxabarber:estoque:${usuario.id}:${filialId}`); } catch { pendente = true; }
  return <Editor key={`${filialId}:${id}`} id={id} filialId={filialId} pendente={pendente} />;
}

function Editor({ id, filialId, pendente }: { id: string; filialId: string; pendente: boolean }) {
  const navigate = useNavigate();
  const [produto, setProduto] = useState<Produto | null>(null);
  const [form, setForm] = useState<Formulario | null>(null);
  const [movimentos, setMovimentos] = useState<Movimento[]>([]);
  const [historicoErro, setHistoricoErro] = useState('');
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const trava = useRef(false);
  const [avisoFoto, setAvisoFoto] = useState('');
  const [incerto, setIncerto] = useState<'edicao' | 'upload' | 'remocao' | null>(null);
  const { conferir, consultando, aviso } = useConferencia();

  useEffect(() => {
    const controller = new AbortController();
    api.get<Produto[]>('/estoque/produtos', { signal: controller.signal, params: { filial_id: filialId } }).then(r => {
      if (controller.signal.aborted) return;
      const p = r.data.find(item => item.id === id);
      if (!p) { setErro('Item não encontrado nesta filial.'); setCarregando(false); return; }
      setProduto(p);
      setForm(formulario(p));
      setCarregando(false);
    }).catch(e => { if (!controller.signal.aborted) { setErro(mensagemErro(e, 'Não foi possível carregar o item.')); setCarregando(false); } });
    api.get<Movimento[]>(`/estoque/produtos/${id}/movimentos`, { signal: controller.signal, params: { filial_id: filialId } }).then(r => { if (!controller.signal.aborted) setMovimentos(r.data); }).catch(e => { if (!controller.signal.aborted) setHistoricoErro(mensagemErro(e, 'Não foi possível carregar o histórico.')); });
    return () => controller.abort();
  }, [id, filialId]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    if (!form || pendente || incerto || trava.current || (!form.venda && !form.consumo)) return;
    trava.current = true; setOcupado(true); setErro('');
    try {
      await api.put(`/estoque/produtos/${id}`, { ...form, preco_venda: form.venda ? form.preco_venda : null, visivel_vitrine: form.venda && !form.consumo && !!form.visivel_vitrine }, { params: { filial_id: filialId } });
      navigate('/estoque', { state: { edicaoConfirmada: 'Alterações do produto salvas.' } });
    } catch (e) {
      if (escritaIncerta(e)) setIncerto('edicao');
      else setErro(mensagemErro(e, 'Não foi possível salvar o item.'));
    }
    finally { trava.current = false; setOcupado(false); }
  }
  async function alterarFoto(arquivo: File | null) {
    if (pendente || incerto || trava.current) return;
    if (arquivo && (!['image/jpeg', 'image/png', 'image/webp'].includes(arquivo.type) || arquivo.size > 8 * 1024 * 1024)) {
      setErro('Selecione uma foto JPEG, PNG ou WebP de até 8 MB.'); return;
    }
    const marca = contextoAtual();
    const caminho = `/estoque/produtos/${id}/foto`;
    const params = { filial_id: filialId };
    trava.current = true; setOcupado(true); setErro(''); setAvisoFoto('');
    try {
      let foto_url = null;
      if (arquivo) {
        const resposta = await api.put<{ foto_url: string }>(caminho, arquivo, { params, headers: { 'Content-Type': arquivo.type } });
        foto_url = resposta.data.foto_url;
      } else await api.delete(caminho, { params });
      if (contextoValido(marca)) {
        setProduto(p => p && { ...p, foto_url });
        setAvisoFoto(arquivo ? 'Foto atualizada.' : 'Foto removida.');
      }
    } catch (falha) {
      if (contextoValido(marca)) {
        if (escritaIncerta(falha)) setIncerto(arquivo ? 'upload' : 'remocao');
        else setErro(mensagemErro(falha, 'Não foi possível alterar a foto.'));
      }
    } finally { trava.current = false; setOcupado(false); }
  }

  if (carregando) return <p role="status">Carregando item...</p>;
  if (!produto || !form) return <p role="alert">{erro} <Link to="/estoque">Voltar ao estoque</Link></p>;
  const preco = form.preco_venda === null || form.preco_venda === '' ? NaN : Number(form.preco_venda);
  const custo = form.custo === '' ? NaN : Number(form.custo);
  const margem = form.venda && Number.isFinite(preco) && preco > 0 && Number.isFinite(custo) ? (preco - custo) / preco * 100 : null;
  const alerta = situacao(produto);
  return <section className="produto-edicao">
    <p className="pe-trilha"><Link to="/estoque">Itens / Estoque</Link> <span>›</span> Editar item <span>›</span> {produto.nome}</p>
    <header className="pe-cabecalho"><div><div className="pe-icone">{icon('inventory_2')}</div><h1>Editar item: {produto.nome}</h1><span className={`pe-status ${alerta}`}>{produto.ativo ? 'Ativo' : 'Inativo'} · {rotulos[alerta]}</span></div><Link className="pe-secundario" to="/estoque">{icon('arrow_back')} Voltar ao estoque</Link></header>
    {erro && <p className="pe-erro" role="alert">{erro}</p>}
    {incerto && <aside><p role="status">O resultado da alteração ainda é incerto.</p>
      <button type="button" disabled={consultando} onClick={() => void conferir(async () => {
        const { data } = await api.get<Produto[]>('/estoque/produtos', { params: { filial_id: filialId } });
        return data.find(item => item.id === id);
      }, atual => {
        if (!atual) return false;
        if (incerto === 'edicao') {
          if (JSON.stringify(normalizar(formulario(atual))) !== JSON.stringify(normalizar(form))) return false;
          navigate('/estoque', { state: { edicaoConfirmada: 'O produto consultado corresponde às alterações enviadas.' } });
          return true;
        }
        setProduto(p => p && { ...p, foto_url: atual.foto_url });
        if (incerto !== 'remocao' || atual.foto_url) return false;
        setIncerto(null); setAvisoFoto('O produto consta sem foto.'); return true;
      })}>{consultando ? 'Conferindo…' : 'Conferir produto'}</button>{aviso && <p role="status">{aviso}</p>}
      {incerto === 'upload' && <p>Confira a foto atual abaixo. A consulta não identifica qual envio publicou a imagem.</p>}
    </aside>}
    {pendente && <p className="pe-erro" role="alert">Recupere a movimentação pendente no estoque antes de salvar alterações. <Link to="/estoque">Voltar ao estoque</Link></p>}
    <form onSubmit={salvar} className="pe-layout">
      <fieldset className="pe-principal pe-campos" disabled={ocupado || !!incerto}>
        <section className="pe-card"><h2>{icon('tune')} Classificação e destinação</h2><p>Selecione uma ou ambas as finalidades do item.</p><ClassificacaoProduto venda={form.venda} consumo={form.consumo} categoria={form.categoria_id ?? null} marca={form.marca_id ?? null} alterar={valores => setForm(atual => atual ? {...atual,...valores} : atual)} /></section>
        <section className="pe-card"><h2>{icon('description')} Dados gerais do produto</h2><div className="pe-grade"><label>Nome do produto<input required maxLength={150} value={form.nome} onChange={e => setForm({...form,nome:e.target.value})} /></label><label>Unidade de medida<input required maxLength={20} value={form.unidade} onChange={e => setForm({...form,unidade:e.target.value})} /><small>A unidade não pode mudar após uma movimentação.</small></label></div><label className="pe-ativo"><input type="checkbox" checked={form.ativo} onChange={e => setForm({...form,ativo:e.target.checked})} /> Item ativo</label></section>
        <section className="pe-card"><h2>{icon('payments')} Precificação, custos e comissão</h2><div className="pe-grade pe-tres"><label>Custo unitário (R$)<input type="number" required min="0" step="0.01" value={form.custo} onChange={e => setForm({...form,custo:e.target.value})} /></label>{form.venda && <><label>Preço de venda (R$)<input type="number" required min="0" step="0.01" value={form.preco_venda ?? ''} onChange={e => setForm({...form,preco_venda:e.target.value})} /></label><label>Comissão padrão (%)<input type="number" required min="0" max="100" step="0.01" value={form.comissao_padrao ?? '0'} onChange={e => setForm({...form,comissao_padrao:e.target.value})} /></label></>}</div><div className="pe-margem"><span>{icon('monitoring')} Margem bruta estimada <small>Calculada com preço e custo, sem descontar comissões ou outras despesas.</small></span><strong>{margem === null ? '—' : `${margem.toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`}</strong></div></section>
        <section className="pe-card"><h2>Vitrine pública</h2>
          <p>A filial publica apenas itens ativos de revenda que não sejam de uso interno.</p>
          <label>Descrição na vitrine<textarea rows={3} maxLength={1000} value={form.descricao_vitrine ?? ''} disabled={ocupado || pendente}
            onChange={e => setForm({ ...form, descricao_vitrine: e.target.value })} /></label>
          <label className="pe-ativo"><input type="checkbox" checked={!!form.visivel_vitrine && form.venda && !form.consumo}
            disabled={!form.venda || form.consumo || ocupado || pendente}
            onChange={e => setForm({ ...form, visivel_vitrine: e.target.checked })} />Visível na vitrine</label>
          {produto.foto_url && <img className="pe-foto" src={produto.foto_url} alt="Foto do produto" />}
          <label>Foto da vitrine<input type="file" accept="image/jpeg,image/png,image/webp" disabled={ocupado || pendente}
            onChange={e => { const arquivo = e.target.files?.[0]; e.target.value = ''; if (arquivo) void alterarFoto(arquivo); }} /></label>
          {produto.foto_url && <button type="button" disabled={ocupado || pendente} onClick={() => void alterarFoto(null)}>Remover foto</button>}
          {avisoFoto && <p role="status">{avisoFoto}</p>}
        </section>
        <section className="pe-card"><h2>{icon('warehouse')} Níveis de estoque</h2><div className="pe-grade"><div className="pe-saldo"><span>Quantidade atual</span><strong>{quantidade(produto.saldo)} <small>{produto.unidade}</small></strong><span>{rotulos[alerta]}</span></div><label>Estoque mínimo<input type="number" required min="0" step="0.001" value={form.estoque_minimo} onChange={e => setForm({...form,estoque_minimo:e.target.value})} /><small>Quantidade de referência para reposição.</small></label></div><Link className="pe-secundario pe-movimentar" to={`/estoque?movimentar=${encodeURIComponent(id)}`}>{icon('swap_vert')} Ajustar estoque</Link></section>
      </fieldset>
      <aside className="pe-lateral"><section className="pe-card"><h2>{icon('history')} Últimas movimentações</h2>{historicoErro ? <p role="alert">{historicoErro}</p> : movimentos.length ? <ol className="pe-historico">{movimentos.slice(0, 5).map(m => <li key={m.id}><strong>{m.tipo} · {quantidade(m.quantidade)} {produto.unidade}</strong><span>{new Date(m.registrado_em).toLocaleString('pt-BR')}</span><p>{m.motivo}</p><small>Saldo: {quantidade(m.saldo_apos)} · Responsável: {m.registrado_por}</small></li>)}</ol> : <p>Nenhuma movimentação registrada.</p>}<Link to={`/estoque?movimentar=${encodeURIComponent(id)}`}>Ver histórico e movimentar →</Link></section></aside>
      <footer className="pe-rodape"><Link className="pe-secundario" to="/estoque">Cancelar alterações</Link><button type="submit" disabled={ocupado || pendente || !!incerto || (!form.venda && !form.consumo)}>{icon('check_circle')} {ocupado ? 'Salvando...' : 'Salvar alterações'}</button></footer>
    </form>
  </section>;
}
