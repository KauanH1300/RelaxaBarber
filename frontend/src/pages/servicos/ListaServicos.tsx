import { useEffect, useState, useRef } from 'react';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { podeGerenciarServicos, useUsuario } from '../../services/usuario';
import { Link, useNavigate } from 'react-router-dom';
import { listarServicos, excluirServico } from '../../services/servico';
import type { Servico } from '../../services/servico';
import './servicos.css';

export function ListaServicos() {
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [erro, setErro] = useState('');
  const navigate = useNavigate();
  const usuario = useUsuario();
  const gerencia = podeGerenciarServicos(usuario);
  const [excluindo, setExcluindo] = useState(false);
  const enviando = useRef(false);
  const [carregando, setCarregando] = useState(true);

  const carregar = () => {
    listarServicos()
      .then((res) => { setServicos(res.data); setErro(''); })
      .catch((falha: unknown) => setErro(mensagemErro(falha, 'Não foi possível carregar os serviços')))
      .finally(() => setCarregando(false));
  };

  useEffect(() => { carregar(); }, []);

  const handleExcluir = async (id: string) => {
    if (!gerencia || enviando.current || carregando) return;
    if (!confirm('Excluir este serviço?')) return;
    enviando.current = true;
    setExcluindo(true);
    setErro('');
    try {
      await excluirServico(id);
      setCarregando(true);
      carregar();
    } catch (e) {
      setErro(mensagemErro(e, 'Erro ao excluir serviço') + (escritaIncerta(e) ? ' Confira os serviços antes de repetir a operação.' : ''));
    } finally {
      enviando.current = false;
      setExcluindo(false);
    }
  };

  return (
    <div className="servicos-container">
      <div className="servicos-cabecalho">
       <h2>Serviços</h2>
       {gerencia && <Link className="servicos-link-novo" to="/servicos/novo">+ Novo serviço</Link>}
      </div>
      {carregando && <p role="status">Carregando serviços...</p>}
      {erro && <><p role="alert" className="servicos-erro">{erro}</p><button disabled={carregando || excluindo} onClick={() => { setCarregando(true); carregar(); }}>Atualizar serviços</button></>}
      <table className="servicos-tabela">
        <tbody>
          {servicos.map((s) => (
            <tr key={s.id}>
              <td>{s.nome}</td>
              <td>{s.preco.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</td>
              <td>{s.tempo_estimado} min</td>
              {gerencia && <td>
                <button disabled={excluindo || carregando} onClick={() => navigate(`/servicos/${s.id}/editar`)}>Editar</button>
                <button disabled={excluindo || carregando} onClick={() => handleExcluir(s.id)}>Excluir</button>
              </td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}