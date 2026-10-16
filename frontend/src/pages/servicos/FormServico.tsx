import { useEffect, useState, useRef } from 'react';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { useNavigate, useParams } from 'react-router-dom';
import { criarServico, atualizarServico, listarServicos } from '../../services/servico';
import type { ServicoInput } from '../../services/servico';
import './servicos.css';

export function FormServico() {
  const { id } = useParams();
  const editando = Boolean(id);
  const navigate = useNavigate();

  const [dados, setDados] = useState<ServicoInput>({
    nome: '', preco: 0, tempo_estimado: 0, comissao_padrao: 0,
  });
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);
  const enviando = useRef(false);
  const [resultadoIncerto, setResultadoIncerto] = useState(false);
  const [carga, setCarga] = useState<{ id: string; erro?: string } | null>(null);
  const [tentativa, setTentativa] = useState(0);
  const carregando = editando && carga?.id !== id;
  const erroCarga = carga?.id === id ? carga?.erro : undefined;

  useEffect(() => {
    if (!id) return;
    let ativo = true;
    listarServicos().then((res) => {
      if (!ativo) return;
      const atual = res.data.find((s) => s.id === id);
      if (atual) { setDados(atual); setCarga({ id }); }
      else setCarga({ id, erro: 'Serviço não encontrado ou inativo.' });
    }).catch((falha: unknown) => {
      if (ativo) setCarga({ id, erro: mensagemErro(falha, 'Não foi possível carregar o serviço') });
    });
    return () => { ativo = false; };
  }, [id, tentativa]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (enviando.current || carregando || erroCarga || resultadoIncerto) return;
    enviando.current = true;
    setSalvando(true);
    setErro('');
    try {
      if (editando) await atualizarServico(id!, dados);
      else await criarServico(dados);
      navigate('/servicos');
    } catch (e) {
      const incerto = escritaIncerta(e);
      setResultadoIncerto(incerto);
      setErro(mensagemErro(e, 'Erro ao salvar serviço') + (incerto ? ' Confira a lista de serviços antes de repetir a operação.' : ''));
    } finally {
      enviando.current = false;
      setSalvando(false);
    }
  };

  if (carregando) return <p role="status">Carregando serviço...</p>;
  if (erroCarga) return <><p role="alert">{erroCarga}</p><button onClick={() => { setCarga(null); setTentativa((n) => n + 1); }}>Tentar novamente</button></>;

  return (
    <form className="servico-form" onSubmit={handleSubmit}>
      <h2>{editando ? 'Editar' : 'Novo'} serviço</h2>
      {erro && <p role="alert" className="servicos-erro">{erro}</p>}

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
        <input disabled={salvando || resultadoIncerto} type="number" step="0.01" placeholder="Ex: 40"
        value={dados.comissao_padrao || ''}
          onChange={(e) => setDados({ ...dados, comissao_padrao: Number(e.target.value) })} required />
      </label>

      <button type="submit" disabled={salvando || resultadoIncerto}>{salvando ? 'Salvando...' : 'Salvar'}</button>
      <button type="button" disabled={salvando} onClick={() => navigate('/servicos')}>Voltar à lista</button>
    </form>
  );
}