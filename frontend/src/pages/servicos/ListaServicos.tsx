import { useEffect, useState } from 'react';
import axios from 'axios';
import { Link, useNavigate } from 'react-router-dom';
import { listarServicos, excluirServico } from '../../services/servico';
import type { Servico } from '../../services/servico';
import '../servicos.css';

export function ListaServicos() {
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [erro, setErro] = useState('');
  const navigate = useNavigate();

  const carregar = () => {
    listarServicos()
      .then((res) => setServicos(res.data))
      .catch(() => setErro('Não foi possível carregar os serviços.'));
  };

  useEffect(() => { carregar(); }, []);

  const handleExcluir = async (id: string) => {
    if (!confirm('Excluir este serviço?')) return;
    try {
      await excluirServico(id);
      carregar();
    } catch (e) {
      const msg = axios.isAxiosError(e) ? e.response?.data?.detail : undefined;
      setErro(msg || 'Erro ao excluir serviço.');
    }
  };

  return (
    <div className="servicos-container">
      <h2>Serviços</h2>
      {erro && <p className="servicos-erro">{erro}</p>}
      <Link className="servicos-link-novo" to="/servicos/novo">+ Novo serviço</Link>
      <table className="servicos-tabela">
        <tbody>
          {servicos.map((s) => (
            <tr key={s.id}>
              <td>{s.nome}</td>
              <td>R$ {s.preco.toFixed(2)}</td>
              <td>{s.tempo_estimado} min</td>
              <td>
                <button onClick={() => navigate(`/servicos/${s.id}/editar`)}>Editar</button>
                <button onClick={() => handleExcluir(s.id)}>Excluir</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}