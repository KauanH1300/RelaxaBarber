import { useEffect, useState, useRef } from 'react';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { criarServico, atualizarServico, consultarServico, conferirCadastroServico } from '../../services/servico';
import type { ServicoAdministrativo, ServicoInput } from '../../services/servico';
import { CategoriasServico } from './CategoriasServico';
import { InsumosServico } from './InsumosServico';
import { useConferencia } from '../../services/useConferencia';
import { useUsuario } from '../../services/usuario';
import './servicos.css';

export function FormServico() {
  const { id } = useParams();
  const editando = Boolean(id);
  const navigate = useNavigate();
  const location = useLocation();
  const usuario = useUsuario();
  const storage = `relaxabarber:servico:cadastro:${usuario.id}`;

  const [dados, setDados] = useState<ServicoInput>({
    nome: '', preco: 0, tempo_estimado: 0, comissao_padrao: 0,
  });
  const [erro, setErro] = useState('');
  const [criandoCategoria, setCriandoCategoria] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const enviando = useRef(false);
  const [chaveInicial] = useState(() => {
    try { return !id ? sessionStorage.getItem(storage) : null; } catch { return null; }
  });
  const [resultadoIncerto, setResultadoIncerto] = useState(!!chaveInicial);
  const [sucesso, setSucesso] = useState('');
  const chaveCadastro = useRef(chaveInicial ?? undefined);
  const { conferir, consultando, aviso } = useConferencia();
  const [carga, setCarga] = useState<{ id: string; erro?: string } | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const carregando = editando && carga?.id !== id;
  const erroCarga = carga?.id === id ? carga?.erro : undefined;

  useEffect(() => {
    if (!id) return;
    let ativo = true;
    consultarServico(id).then((res) => {
      if (!ativo) return;
      const { nome, preco, tempo_estimado, comissao_padrao, categorias } = res.data;
      setDados({ nome, preco, tempo_estimado, comissao_padrao, categorias_ids: categorias?.map(item => item.id) ?? [] });
      setCarga({ id });
    }).catch((falha: unknown) => {
      if (ativo) setCarga({ id, erro: mensagemErro(falha, 'Não foi possível carregar o serviço') });
    });
    return () => { ativo = false; };
  }, [id, tentativa]);

  function confirmar(servico: ServicoAdministrativo) {
    setResultadoIncerto(false);
    if (id) {
      setSucesso('Serviço atualizado com sucesso.');
    } else {
      try { sessionStorage.removeItem(storage); } catch { /* A chave continua consultável. */ }
      navigate(`/servicos/${servico.id}/editar`, { replace: true, state: { cadastroConfirmado: true } });
    }
  }

  async function conferirServico() {
    const chave = chaveCadastro.current;
    await conferir(async () => id ? (await consultarServico(id)).data :
      chave ? (await conferirCadastroServico(chave)).data : undefined, atual => {
      const categoriasAtuais = new Set(atual?.categorias?.map(item => item.id));
      const categoriasEsperadas = new Set(dados.categorias_ids);
      const mesmosVinculos = categoriasAtuais.size === categoriasEsperadas.size &&
        [...categoriasEsperadas].every(categoria => categoriasAtuais.has(categoria));
      if (!atual?.id || (id && (atual.id !== id || atual.nome !== dados.nome.trim() ||
        atual.preco !== dados.preco || atual.tempo_estimado !== dados.tempo_estimado ||
        atual.comissao_padrao !== dados.comissao_padrao || !mesmosVinculos))) return false;
      confirmar(atual);
      return true;
    });
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (enviando.current || carregando || erroCarga || resultadoIncerto || criandoCategoria) return;
    enviando.current = true;
    setSalvando(true);
    setErro('');
    setSucesso('');
    try {
      if (!id) {
        chaveCadastro.current = crypto.randomUUID();
        sessionStorage.setItem(storage, chaveCadastro.current);
      }
      const { data } = id ? await atualizarServico(id, dados) : await criarServico(dados, chaveCadastro.current);
      confirmar(data);
    } catch (e) {
      const incerto = escritaIncerta(e);
      setResultadoIncerto(incerto);
      if (!incerto) {
        if (!id) { try { sessionStorage.removeItem(storage); } catch { /* Nenhum reenvio automático. */ } }
        setErro(mensagemErro(e, 'Erro ao salvar serviço'));
      }
    } finally {
      enviando.current = false;
      setSalvando(false);
    }
  };

  if (carregando) return <p role="status">Carregando serviço...</p>;
  if (erroCarga) return <><p role="alert">{erroCarga}</p><button onClick={() => { setCarga(null); setTentativa((n) => n + 1); }}>Tentar novamente</button></>;

  return (
    <>
    <form className="servico-form" onSubmit={handleSubmit}>
      <h2>{editando ? 'Editar' : 'Novo'} serviço</h2>
      {erro && <p role="alert" className="servicos-erro">{erro}</p>}
      {sucesso && <p role="status">{sucesso}</p>}
      {location.state?.cadastroConfirmado && !sucesso && !resultadoIncerto && !salvando && !erro && <p role="status">Serviço cadastrado com sucesso.</p>}
      {resultadoIncerto && <><p role="status">Resultado não confirmado. Confira sem reenviar.</p>
        <button type="button" disabled={consultando} onClick={() => void conferirServico()}>{consultando ? 'Conferindo…' : 'Conferir resultado'}</button>
        {aviso && <p role="status">{aviso}</p>}</>}

      <label>
        Nome
        <input disabled={salvando || resultadoIncerto} placeholder="Ex: Corte de cabelo" value={dados.nome}
          onChange={(e) => setDados({ ...dados, nome: e.target.value })} required />
      </label>

      <label>
        Preço (R$)
        <input disabled={salvando || resultadoIncerto} type="number" min={0} max={99999999.99} step="0.01" placeholder="Ex: 50.00"
         value={dados.preco}
          onChange={(e) => setDados({ ...dados, preco: Number(e.target.value) })} required />
      </label>

      <label>
        Tempo estimado (min)
        <input disabled={salvando || resultadoIncerto} type="number" min={1} max={480} step={1} placeholder="Ex: 30"
         value={dados.tempo_estimado || ''}
          onChange={(e) => setDados({ ...dados, tempo_estimado: Number(e.target.value) })} required />
      </label>

      <label>
        Comissão padrão (%)
        <input disabled={salvando || resultadoIncerto} type="number" min={0} max={100} step="0.01" placeholder="Ex: 40"
        value={dados.comissao_padrao}
          onChange={(e) => setDados({ ...dados, comissao_padrao: Number(e.target.value) })} required />
      </label>

      <CategoriasServico key={id ?? 'novo'} selecionadas={dados.categorias_ids ?? []}
        alterar={categorias_ids => setDados(atuais => ({ ...atuais, categorias_ids }))}
        informarCriacao={setCriandoCategoria} bloqueado={salvando || resultadoIncerto} />

      <button type="submit" disabled={salvando || resultadoIncerto || criandoCategoria}>{salvando ? 'Salvando...' : editando ? 'Salvar' : 'Salvar e configurar insumos'}</button>
      <button type="button" disabled={salvando || consultando} onClick={() => navigate('/servicos')}>Voltar à lista</button>
    </form>
    {id && <InsumosServico key={id} servicoId={id} />}
    </>
  );
}
