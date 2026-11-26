import { useEffect, useState } from 'react';
import { criarCategoriaServico, listarCategoriasServico, type CategoriaServico } from '../../services/servico';
import { mensagemErro } from '../../services/erros';

export function CategoriasServico({ selecionadas, alterar, informarCriacao, bloqueado }: {
  selecionadas: string[];
  alterar: (ids: string[]) => void;
  informarCriacao: (criando: boolean) => void;
  bloqueado: boolean;
}) {
  const [categorias, setCategorias] = useState<CategoriaServico[]>([]);
  const [nome, setNome] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [criando, setCriando] = useState(false);
  const [erro, setErro] = useState('');
  const [tentativa, setTentativa] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listarCategoriasServico(controller.signal).then(({ data }) => {
      if (!controller.signal.aborted) setCategorias(data);
    }).catch(() => {
      if (!controller.signal.aborted) setErro('Não foi possível carregar as categorias.');
    }).finally(() => {
      if (!controller.signal.aborted) setCarregando(false);
    });
    return () => controller.abort();
  }, [tentativa]);

  async function cadastrar() {
    if (!nome.trim() || criando || bloqueado || carregando) return;
    setCriando(true);
    informarCriacao(true);
    setErro('');
    try {
      const { data } = await criarCategoriaServico(nome.trim());
      setCategorias(atuais => atuais.some(item => item.id === data.id) ? atuais
        : [...atuais, data].sort((a, b) => a.nome.localeCompare(b.nome, 'pt-BR')));
      alterar([...new Set([...selecionadas, data.id])]);
      setNome('');
    } catch (falha) {
      setErro(mensagemErro(falha, 'Não foi possível criar a categoria.'));
    } finally {
      setCriando(false);
      informarCriacao(false);
    }
  }

  return <fieldset disabled={bloqueado || criando} className="grid gap-2">
    <legend>Categorias do serviço</legend>
    <p>Selecione as categorias e salve o serviço para confirmar os vínculos.</p>
    {carregando && <p role="status">Carregando categorias…</p>}
    {erro && <div><p role="alert">{erro}</p>
      <button type="button" onClick={() => {
        setErro('');
        setCarregando(true);
        setTentativa(atual => atual + 1);
      }}>Recarregar categorias</button>
    </div>}
    <div className="grid gap-2">
      {categorias.map(categoria => <label key={categoria.id} className="servico-categoria-opcao items-center">
        <input className="w-auto" type="checkbox" checked={selecionadas.includes(categoria.id)}
          onChange={evento => alterar(evento.target.checked
            ? [...selecionadas, categoria.id] : selecionadas.filter(id => id !== categoria.id))} />
        {categoria.nome}
      </label>)}
    </div>
    <label>Nova categoria
      <input value={nome} maxLength={80} onChange={evento => setNome(evento.target.value)}
        onKeyDown={evento => {
          if (evento.key !== 'Enter') return;
          evento.preventDefault();
          void cadastrar();
        }} />
    </label>
    <button type="button" disabled={!nome.trim() || carregando} onClick={() => void cadastrar()}>
      {criando ? 'Criando…' : 'Criar categoria'}
    </button>
  </fieldset>;
}
