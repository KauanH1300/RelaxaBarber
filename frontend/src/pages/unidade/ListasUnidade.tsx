import { useEffect, useState } from 'react';
import api from '../../services/api';
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
  const lista = useLista<{ id: string; nome: string; telefone: string }>('/clientes');
  return <section><h1>Clientes da unidade</h1>
    {lista.carregando && <p role="status">Carregando clientes...</p>}
    {lista.erro && <p role="alert">{lista.erro}</p>}
    <button onClick={lista.recarregar}>Atualizar clientes</button>
    {!lista.carregando && !lista.erro && !lista.registros.length && <p>Nenhum cliente vinculado.</p>}
    <ul>{lista.registros.map((cliente) => <li key={cliente.id}>{cliente.nome} — {cliente.telefone}</li>)}</ul>
  </section>;
}

export function ComandasUnidade() {
  const lista = useLista<{ id: string; status: string }>('/comandas');
  return <section><h1>Comandas da unidade</h1>
    {lista.carregando && <p role="status">Carregando comandas...</p>}
    {lista.erro && <p role="alert">{lista.erro}</p>}
    <button onClick={lista.recarregar}>Atualizar comandas</button>
    {!lista.carregando && !lista.erro && !lista.registros.length && <p>Nenhuma comanda disponível.</p>}
    <ul>{lista.registros.map((comanda) => <li key={comanda.id}>Comanda {comanda.id} — {comanda.status}</li>)}</ul>
  </section>;
}
