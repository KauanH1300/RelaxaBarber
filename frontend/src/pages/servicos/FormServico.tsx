import { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import { criarServico, atualizarServico, listarServicos } from '../../services/servico';
import type { ServicoInput } from '../../services/servico';
import '../servicos.css';

export function FormServico() {
  const { id } = useParams();
  const editando = Boolean(id);
  const navigate = useNavigate();

  const [dados, setDados] = useState<ServicoInput>({
    nome: '', preco: 0, tempo_estimado: 0, comissao_padrao: 0,
  });
  const [erro, setErro] = useState('');

  useEffect(() => {
    if (editando) {
      listarServicos().then((res) => {
        const atual = res.data.find((s) => s.id === id);
        if (atual) setDados(atual);
      });
    }
  }, [id, editando]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErro('');
    try {
      if (editando) await atualizarServico(id!, dados);
      else await criarServico(dados);
      navigate('/servicos');
    } catch (e) {
      const msg = axios.isAxiosError(e) ? e.response?.data?.detail : undefined;
      setErro(msg || 'Erro ao salvar serviço.');
    }
  };

  return (
    <form className="servico-form" onSubmit={handleSubmit}>
      <h2>{editando ? 'Editar' : 'Novo'} serviço</h2>
      {erro && <p className="servicos-erro">{erro}</p>}

      <label>
        Nome
        <input placeholder="Ex: Corte de cabelo" value={dados.nome}
          onChange={(e) => setDados({ ...dados, nome: e.target.value })} required />
      </label>

      <label>
        Preço (R$)
        <input type="number" step="0.01" value={dados.preco}
          onChange={(e) => setDados({ ...dados, preco: Number(e.target.value) })} required />
      </label>

      <label>
        Tempo estimado (min)
        <input type="number" value={dados.tempo_estimado}
          onChange={(e) => setDados({ ...dados, tempo_estimado: Number(e.target.value) })} required />
      </label>

      <label>
        Comissão padrão (%)
        <input type="number" step="0.01" value={dados.comissao_padrao}
          onChange={(e) => setDados({ ...dados, comissao_padrao: Number(e.target.value) })} required />
      </label>

      <button type="submit">Salvar</button>
    </form>
  );
}