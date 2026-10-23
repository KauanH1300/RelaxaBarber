import { useEffect, useState } from 'react';
import api from '../../services/api';
import { useUsuario } from '../../services/usuario';
import { ResumoClientePerfil } from './ResumoClientePerfil';
import { mensagemErro } from '../../services/erros';

function useLista<T>(endpoint: string) {
  const [registros, setRegistros] = useState<T[]>([]);
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [tentativa, setTentativa] = useState(0);
  useEffect(() => {
    let ativo = true;
    api.get<T[]>(endpoint).then(({ data }) => {
      if (ativo) { setRegistros(data); setErro(''); }
    }).catch((falha) => {
      if (ativo) { setRegistros([]); setErro(mensagemErro(falha, 'Não foi possível carregar os dados da unidade')); }
    }).finally(() => { if (ativo) setCarregando(false); });
    return () => { ativo = false; };
  }, [endpoint, tentativa]);
  function recarregar() { setCarregando(true); setTentativa((n) => n + 1); }
  return { registros, erro, carregando, recarregar };
}

export function ClientesUnidade() {
  const usuario = useUsuario();
  const [selecionado, setSelecionado] = useState<{ id: string; nome: string } | null>(null);
  const lista = useLista<{ id: string; nome: string; telefone: string }>('/clientes');
  return <section><h1>Clientes da unidade</h1>
    {lista.carregando && <p role="status">Carregando clientes...</p>}
    {lista.erro && <p role="alert">{lista.erro}</p>}
    <button onClick={lista.recarregar}>Atualizar clientes</button>
    {!lista.carregando && !lista.erro && !lista.registros.length && <p>Nenhum cliente vinculado.</p>}
    <ul>{lista.registros.map((cliente) => <li key={cliente.id}>{cliente.nome} — {cliente.telefone} <button onClick={() => setSelecionado(cliente)}>Ver perfil</button></li>)}</ul>
    {selecionado && <section><h2>{selecionado.nome}</h2>
      <button onClick={() => setSelecionado(null)}>Fechar perfil</button>
      <ResumoClientePerfil key={`${selecionado.id}:${usuario.perfil}`} clienteId={selecionado.id} administrador={usuario.perfil === 'admin'} />
    </section>}
  </section>;
}
