import { useEffect, useState } from 'react';
import api from '../../services/api';
import { useFilial } from '../../services/filialEstado';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { useConferencia } from '../../services/useConferencia';

type Excecao = { id: string; servico_id: string | null; produto_id: string | null; percentual: string; ativo: boolean };
type Item = { id: string; nome: string; ativo: boolean; venda?: boolean };
export function ComissoesFuncionario({ profissionalId }: { profissionalId: string }) {
  const { filialId } = useFilial();
  const [servicos, setServicos] = useState<Item[]>([]); const [produtos, setProdutos] = useState<Item[]>([]);
  const [excecoes, setExcecoes] = useState<Excecao[]>([]); const [item, setItem] = useState('');
  const [percentual, setPercentual] = useState('0'); const [ativo, setAtivo] = useState(true);
  const [erro, setErro] = useState(''); const [ocupado, setOcupado] = useState(true);
  const [incerto, setIncerto] = useState(false);
  const [sucesso, setSucesso] = useState('');
  const { conferir, consultando, aviso } = useConferencia();
  const url = `/comissoes/profissionais/${profissionalId}`;
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api.get<Item[]>('/servicos/', { signal: controller.signal }), api.get<Item[]>('/estoque/produtos', { signal: controller.signal }), api.get<Excecao[]>(`/comissoes/profissionais/${profissionalId}`, { signal: controller.signal })]).then(([a,b,c]) => {
      if (!controller.signal.aborted) { setServicos(a.data); setProdutos(b.data.filter(p => p.ativo && p.venda)); setExcecoes(c.data); setErro(''); }
    }).catch(e => { if (!controller.signal.aborted) setErro(mensagemErro(e, 'Não foi possível consultar as comissões')); }).finally(() => { if (!controller.signal.aborted) setOcupado(false); });
    return () => controller.abort();
  }, [profissionalId, filialId]);
  function selecao() {
    const [tipo, id] = item.split(':');
    return { servico_id: tipo === 'servico' ? id : null, produto_id: tipo === 'produto' ? id : null, percentual, ativo };
  }
  async function salvar(e: React.FormEvent) {
    e.preventDefault(); if (ocupado || incerto || !item) return;
    setOcupado(true); setErro(''); setSucesso('');
    try {
      const { data } = await api.put<Excecao>(url, selecao());
      setExcecoes(itens => [...itens.filter(x => x.id !== data.id), data]);
      setSucesso('Exceção de comissão salva.');
    } catch (e) {
      if (escritaIncerta(e)) setIncerto(true);
      else setErro(mensagemErro(e, 'Não foi possível salvar a comissão.'));
    } finally { setOcupado(false); }
  }
  return <section className="funcionario-form" aria-label="Comissões por item"><h3>Comissões por item</h3><p>Exceções valem para a filial selecionada; quando inativas, prevalece a comissão padrão.</p>{erro && <p role="alert">{erro}</p>}
    {ocupado && <p role="status">Aguarde a consulta ou a confirmação do salvamento…</p>}
    {sucesso && <p role="status">{sucesso}</p>}
    {incerto && <><p role="status">Resultado incerto. Confira a exceção atual antes de continuar.</p>
      <button type="button" disabled={consultando} onClick={() => {
        const esperado = selecao();
        void conferir(async () => (await api.get<Excecao[]>(url)).data, atuais => {
          const atual = atuais.find(x => x.servico_id === esperado.servico_id && x.produto_id === esperado.produto_id);
          if (!atual || Number(atual.percentual) !== Number(esperado.percentual) || atual.ativo !== esperado.ativo) return false;
          setExcecoes(atuais); setIncerto(false); setSucesso('A exceção atual corresponde aos dados enviados.'); return true;
        });
      }}>{consultando ? 'Conferindo…' : 'Conferir comissão'}</button>{aviso && <p role="status">{aviso}</p>}</>}
    <form onSubmit={salvar}><fieldset disabled={ocupado || incerto}><label>Serviço ou produto<select required value={item} onChange={e => { const valor=e.target.value; setItem(valor); const [tipo,id]=valor.split(':'); const atual=excecoes.find(x => tipo==='servico' ? x.servico_id===id : x.produto_id===id); setPercentual(atual ? String(atual.percentual) : '0'); setAtivo(atual?.ativo ?? true); }}><option value="">Selecione</option><optgroup label="Serviços">{servicos.filter(s => s.ativo).map(s => <option key={s.id} value={`servico:${s.id}`}>{s.nome}</option>)}</optgroup><optgroup label="Produtos para venda">{produtos.map(p => <option key={p.id} value={`produto:${p.id}`}>{p.nome}</option>)}</optgroup></select></label>
      <label>Comissão (%)<input required type="number" min="0" max="100" step="0.01" value={percentual} onChange={e => setPercentual(e.target.value)} /></label><label><input type="checkbox" checked={ativo} onChange={e => setAtivo(e.target.checked)} /> Exceção ativa</label><button type="submit">Salvar exceção</button></fieldset></form>
    <ul>{excecoes.map(x => <li key={x.id}>{(x.servico_id ? servicos.find(s => s.id === x.servico_id)?.nome : produtos.find(p => p.id === x.produto_id)?.nome) ?? 'Item indisponível'} · {x.percentual}% · {x.ativo ? 'Ativa' : 'Inativa'}</li>)}</ul>
  </section>;
}
