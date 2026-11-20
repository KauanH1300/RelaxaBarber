import { useEffect, useState, useRef } from 'react';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { podeGerenciarServicos, useUsuario } from '../../services/usuario';
import { Link, useNavigate } from 'react-router-dom';
import { listarServicos, excluirServico, consultarServico } from '../../services/servico';
import { useConferencia } from '../../services/useConferencia';
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
  const [incerto, setIncerto] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState('');
  const { conferir, consultando, aviso } = useConferencia();

  const carregar = () => {
    listarServicos()
      .then((res) => { setServicos(res.data); setErro(''); })
      .catch((falha: unknown) => setErro(mensagemErro(falha, 'Não foi possível carregar os serviços')))
      .finally(() => setCarregando(false));
  };

  useEffect(() => { carregar(); }, []);

  const handleExcluir = async (id: string) => {
    if (!gerencia || enviando.current || carregando || incerto) return;
    if (!confirm('Inativar este serviço? Ele deixará de aparecer na lista de serviços ativos. O histórico será preservado.')) return;
    enviando.current = true;
    setExcluindo(true);
    setErro(''); setSucesso('');
    try {
      await excluirServico(id);
      setServicos(itens => itens.filter(s => s.id !== id));
      setSucesso('Serviço inativado.');
      setCarregando(true);
      carregar();
    } catch (e) {
      if (escritaIncerta(e)) setIncerto(id);
      else setErro(mensagemErro(e, 'Não foi possível inativar o serviço'));
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
      {excluindo && <p role="status">Inativando serviço…</p>}
      {sucesso && <p role="status">{sucesso}</p>}
      {incerto && <><p role="status">A inativação ainda não foi confirmada.</p>
        <button type="button" disabled={consultando} onClick={() => void conferir(
          async () => (await consultarServico(incerto)).data, atual => {
            if (atual.id !== incerto || atual.ativo !== false) return false;
            setIncerto(null); setServicos(itens => itens.filter(s => s.id !== atual.id));
            setSucesso('O serviço consta como inativo.'); return true;
          })}>{consultando ? 'Conferindo…' : 'Conferir inativação'}</button>{aviso && <p role="status">{aviso}</p>}</>}
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
                <button disabled={excluindo || carregando || !!incerto} onClick={() => handleExcluir(s.id)}>Inativar</button>
              </td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
