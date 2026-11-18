import { useEffect, useState } from 'react';
import api from '../../services/api';
import { mensagemErro } from '../../services/erros';
import { useFilial } from '../../services/filialEstado';
import './ClassificacaoProduto.css';

type Opcao = { id: string; nome: string };
type Props = { venda: boolean; consumo: boolean; categoria: string | null; marca: string | null; alterar: (valores: { venda?: boolean; consumo?: boolean; categoria_id?: string | null; marca_id?: string | null }) => void };
export function ClassificacaoProduto({ venda, consumo, categoria, marca, alterar }: Props) {
  const { filialId } = useFilial();
  const [categorias, setCategorias] = useState<Opcao[]>([]);
  const [marcas, setMarcas] = useState<Opcao[]>([]);
  const [criando, setCriando] = useState<'categorias' | 'marcas' | null>(null);
  const [nome, setNome] = useState('');
  const [erro, setErro] = useState('');
  const [ocupado, setOcupado] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(['categorias', 'marcas'].map(tipo => api.get<Opcao[]>(`/estoque/catalogos/${tipo}`, { signal: controller.signal, params: { filial_id: filialId } }))).then(([a,b]) => { if (!controller.signal.aborted) { setCategorias(a.data); setMarcas(b.data); } }).catch(e => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Não foi possível carregar categorias e marcas.')); });
    return () => controller.abort();
  }, [filialId]);
  async function criar() {
    if (!criando || !nome.trim() || ocupado) return;
    setOcupado(true); setErro('');
    try {
      const r = await api.post<Opcao>(`/estoque/catalogos/${criando}`, { nome: nome.trim() }, { params: { filial_id: filialId } });
      if (criando === 'categorias') { setCategorias(c => [...c, r.data]); alterar({ categoria_id: r.data.id }); }
      else { setMarcas(c => [...c, r.data]); alterar({ marca_id: r.data.id }); }
      setNome(''); setCriando(null);
    } catch (e) { setErro(mensagemErro(e, 'Não foi possível cadastrar.')); }
    finally { setOcupado(false); }
  }
  return <div className="cp-classificacao">
    <div className="cp-cartoes">{([['venda','shopping_bag','Venda ao cliente','Produto disponível para venda.',venda],['consumo','content_cut','Uso interno','Material utilizado na operação.',consumo]] as const).map(([campo,icone,titulo,descricao,ativo]) => <label key={campo} className={`cp-cartao ${ativo ? 'selecionado' : ''}`}><input type="checkbox" checked={ativo} onChange={e => alterar({ [campo]: e.target.checked })} /><span className="cp-selecao" aria-hidden="true">{ativo ? '✓' : ''}</span><span className="material-symbols-outlined cp-icone" aria-hidden="true">{icone}</span><strong>{titulo}</strong><span>{descricao}</span></label>)}</div>
    {!venda && !consumo && <p className="cp-erro" role="alert">Selecione ao menos uma finalidade.</p>}
    <div className="cp-catalogos">{([['categorias','Categoria',categoria,categorias],['marcas','Marca',marca,marcas]] as const).map(([tipo,rotulo,valor,opcoes]) => <div key={tipo} className="cp-catalogo"><label>{rotulo} (opcional)<select value={valor ?? ''} onChange={e => alterar(tipo === 'categorias' ? { categoria_id:e.target.value || null } : { marca_id:e.target.value || null })}><option value="">Nenhuma</option>{opcoes.map(o => <option key={o.id} value={o.id}>{o.nome}</option>)}</select></label><button type="button" onClick={() => { setCriando(tipo); setNome(''); setErro(''); }}>+ Nova {rotulo.toLowerCase()}</button></div>)}</div>
    {criando && <div className="cp-novo"><label>Nome da {criando === 'categorias' ? 'categoria' : 'marca'}<input maxLength={100} value={nome} onChange={e => setNome(e.target.value)} /></label><button type="button" disabled={ocupado || !nome.trim()} onClick={() => void criar()}>Cadastrar</button><button type="button" disabled={ocupado} onClick={() => {setCriando(null);setErro('');}}>Cancelar</button></div>}
    {erro && <p className="cp-erro" role="alert">{erro}</p>}
  </div>;
}
