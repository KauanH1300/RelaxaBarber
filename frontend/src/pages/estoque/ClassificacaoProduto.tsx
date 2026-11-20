import { useEffect, useState } from 'react';
import api from '../../services/api';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { useConferencia } from '../../services/useConferencia';
import axios from 'axios';
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
  const [carregando, setCarregando] = useState(true);
  const [incerto, setIncerto] = useState(false);
  const [sucesso, setSucesso] = useState('');
  const { conferir, consultando, aviso } = useConferencia();
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(['categorias', 'marcas'].map(tipo => api.get<Opcao[]>(`/estoque/catalogos/${tipo}`, { signal: controller.signal, params: { filial_id: filialId } })))
      .then(([a,b]) => { if (!controller.signal.aborted) { setCategorias(a.data); setMarcas(b.data); } })
      .catch(e => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Não foi possível carregar categorias e marcas.')); })
      .finally(() => { if (!controller.signal.aborted) setCarregando(false); });
    return () => controller.abort();
  }, [filialId]);
  function selecionar(tipo: 'categorias' | 'marcas', opcao: Opcao) {
    if (tipo === 'categorias') { setCategorias(c => [...c.filter(x => x.id !== opcao.id), opcao]); alterar({ categoria_id: opcao.id }); }
    else { setMarcas(c => [...c.filter(x => x.id !== opcao.id), opcao]); alterar({ marca_id: opcao.id }); }
    setNome(''); setCriando(null); setIncerto(false);
  }
  async function criar() {
    if (!criando || !nome.trim() || carregando || ocupado || incerto) return;
    setOcupado(true); setErro(''); setSucesso('');
    try {
      const r = await api.post<Opcao>(`/estoque/catalogos/${criando}`, { nome: nome.trim() }, { params: { filial_id: filialId } });
      selecionar(criando, r.data);
      setSucesso(criando === 'categorias' ? 'Categoria cadastrada e selecionada.' : 'Marca cadastrada e selecionada.');
    } catch (e) {
      const incerta = escritaIncerta(e);
      if (!incerta) setErro(mensagemErro(e, 'Não foi possível cadastrar.'));
      if (incerta || (axios.isAxiosError(e) && e.response?.status === 409)) setIncerto(true);
    }
    finally { setOcupado(false); }
  }
  return <div className="cp-classificacao">
    {carregando && <p role="status">Carregando categorias e marcas…</p>}
    <div className="cp-cartoes">{([['venda','shopping_bag','Venda ao cliente','Produto disponível para venda.',venda],['consumo','content_cut','Uso interno','Material utilizado na operação.',consumo]] as const).map(([campo,icone,titulo,descricao,ativo]) => <label key={campo} className={`cp-cartao ${ativo ? 'selecionado' : ''}`}><input type="checkbox" checked={ativo} onChange={e => alterar({ [campo]: e.target.checked })} /><span className="cp-selecao" aria-hidden="true">{ativo ? '✓' : ''}</span><span className="material-symbols-outlined cp-icone" aria-hidden="true">{icone}</span><strong>{titulo}</strong><span>{descricao}</span></label>)}</div>
    {!venda && !consumo && <p className="cp-erro" role="alert">Selecione ao menos uma finalidade.</p>}
    <div className="cp-catalogos">{([['categorias','Categoria',categoria,categorias],['marcas','Marca',marca,marcas]] as const).map(([tipo,rotulo,valor,opcoes]) => <div key={tipo} className="cp-catalogo"><label>{rotulo} (opcional)<select value={valor ?? ''} onChange={e => alterar(tipo === 'categorias' ? { categoria_id:e.target.value || null } : { marca_id:e.target.value || null })}><option value="">Nenhuma</option>{opcoes.map(o => <option key={o.id} value={o.id}>{o.nome}</option>)}</select></label><button type="button" disabled={carregando || ocupado || incerto} onClick={() => { setCriando(tipo); setNome(''); setErro(''); }}>+ Nova {rotulo.toLowerCase()}</button></div>)}</div>
    {criando && <div className="cp-novo"><label>Nome da {criando === 'categorias' ? 'categoria' : 'marca'}<input maxLength={100} value={nome} disabled={ocupado || incerto} onChange={e => setNome(e.target.value)} /></label><button type="button" disabled={ocupado || incerto || !nome.trim()} onClick={() => void criar()}>{ocupado ? 'Cadastrando…' : 'Cadastrar'}</button><button type="button" disabled={ocupado || incerto} onClick={() => {setCriando(null);setErro('');}}>Cancelar</button></div>}
    {criando && incerto && <><p role="status">Confira se o nome exato já consta no catálogo da filial.</p>
      <button type="button" disabled={consultando} onClick={() => void conferir(
        async () => (await api.get<Opcao[]>(`/estoque/catalogos/${criando}`, { params: { filial_id: filialId } })).data, atuais => {
          const chave = nome.trim().toLowerCase();
          const iguais = atuais.filter(x => x.nome.trim().toLowerCase() === chave);
          if (iguais.length !== 1) return false;
          selecionar(criando, iguais[0]); setErro(''); setSucesso('Registro encontrado no catálogo e selecionado.'); return true;
        })}>{consultando ? 'Conferindo…' : 'Conferir catálogo'}</button>{aviso && <p role="status">{aviso}</p>}</>}
    {sucesso && <p role="status">{sucesso}</p>}
    {erro && <p className="cp-erro" role="alert">{erro}</p>}
  </div>;
}
