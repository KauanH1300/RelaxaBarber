import { useEffect, useRef, useState } from 'react';
import api from '../../services/api';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { mensagemErro } from '../../services/erros';
import { useFilial } from '../../services/filialEstado';

interface Produto {
  id: string;
  nome: string;
  unidade: string;
  ativo: boolean;
  consumo: boolean;
}
interface Insumo { produto_id: string; quantidade: string }

export function InsumosServico({ servicoId }: { servicoId: string }) {
  const { filialId } = useFilial();
  return filialId && <Editor key={filialId} filialId={filialId} servicoId={servicoId} />;
}

function Editor({ servicoId, filialId }: { servicoId: string; filialId: string }) {
  const [produtos, setProdutos] = useState<Produto[]>([]);
  const [itens, setItens] = useState<Insumo[] | null>(null);
  const [erro, setErro] = useState('');
  const [sucesso, setSucesso] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [tentativa, setTentativa] = useState(0);
  const [produto, setProduto] = useState('');
  const trava = useRef(false);
  const url = `/servicos/${servicoId}/insumos`;
  useEffect(() => {
    const controller = new AbortController();
    const config = { params: { filial_id: filialId }, signal: controller.signal };
    Promise.all([api.get<Produto[]>('/estoque/produtos', config), api.get<Insumo[]>(url, config)])
      .then(([estoque, insumos]) => {
        if (!controller.signal.aborted) { setProdutos(estoque.data); setItens(insumos.data); setErro(''); }
      })
      .catch(falha => { if (!controller.signal.aborted) setErro(mensagemErro(falha, 'Não foi possível carregar os insumos.')); });
    return () => controller.abort();
  }, [url, filialId, tentativa]);

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (trava.current || !itens) return;
    const contexto = contextoAtual();
    trava.current = true; setSalvando(true); setErro(''); setSucesso('');
    try {
      const { data } = await api.put<Insumo[]>(url, itens, { params: { filial_id: filialId } });
      if (contextoValido(contexto)) { setItens(data); setSucesso('Insumos salvos.'); }
    } catch (falha) {
      if (contextoValido(contexto)) setErro(mensagemErro(falha, 'Não foi possível salvar os insumos.'));
    } finally {
      trava.current = false; setSalvando(false);
    }
  }

  const disponiveis = produtos.filter(p => p.ativo && p.consumo && !itens?.some(i => i.produto_id === p.id));
  return <form className="servico-form" aria-label="Insumos do serviço" onSubmit={salvar}>
    <h2>Insumos do serviço na filial ativa</h2>
    {erro && <p role="alert">{erro}</p>}
    {sucesso && <p role="status">{sucesso}</p>}
    {!itens ? erro
      ? <button type="button" onClick={() => { setErro(''); setTentativa(n => n + 1); }}>Tentar novamente</button>
      : <p role="status">Carregando insumos…</p>
      : <fieldset disabled={salvando}>
        {itens.map(i => {
          const p = produtos.find(x => x.id === i.produto_id);
          return <div key={i.produto_id}>
            <label>{p?.nome ?? 'Insumo indisponível'} ({p?.unidade ?? 'unidade de estoque'})
              <input type="number" min="0.001" max="99999999999.999" step="0.001" required value={i.quantidade}
                onChange={e => setItens(itens.map(x => x === i ? { ...x, quantidade: e.target.value } : x))} />
            </label>
            <button type="button" onClick={() => setItens(itens.filter(x => x !== i))}>Remover</button>
          </div>;
        })}
        <label>Insumo de uso interno<select value={produto} onChange={e => setProduto(e.target.value)}>
          <option value="">Selecione</option>
          {disponiveis.map(p => <option key={p.id} value={p.id}>{p.nome} ({p.unidade})</option>)}
        </select></label>
        <button type="button" disabled={!disponiveis.some(p => p.id === produto) || itens.length >= 100}
          onClick={() => { setItens([...itens, { produto_id: produto, quantidade: '1' }]); setProduto(''); }}>Adicionar insumo</button>
        <button type="submit">{salvando ? 'Salvando…' : 'Salvar insumos'}</button>
      </fieldset>}
  </form>;
}
