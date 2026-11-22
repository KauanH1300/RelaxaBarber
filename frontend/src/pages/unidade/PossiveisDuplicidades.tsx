import { useEffect, useId, useState } from 'react';
import { erroCliente, listarDuplicidades } from '../../services/clientes';
import type { GrupoDuplicidade } from '../../services/clientes';

export function PossiveisDuplicidades({ filialId, selecionar }: {
  filialId: string; selecionar: (id: string) => void;
}) {
  const [grupos, setGrupos] = useState<GrupoDuplicidade[] | null>(null);
  const [erro, setErro] = useState('');
  const [tentativa, setTentativa] = useState(0);
  const titulo = useId();
  useEffect(() => {
    const controller = new AbortController();
    listarDuplicidades(filialId, controller.signal).then(resultado => {
      if (!controller.signal.aborted) setGrupos(resultado);
    }).catch(falha => {
      if (!controller.signal.aborted) setErro(erroCliente(falha, 'Não foi possível consultar possíveis duplicidades'));
    });
    return () => controller.abort();
  }, [filialId, tentativa]);
  return <section aria-labelledby={titulo} className="cliente-detalhe">
    <h3 id={titulo}>Possíveis duplicidades nesta unidade</h3>
    {erro ? <>
      <p role="alert">{erro}</p>
      <button type="button" onClick={() => { setErro(''); setTentativa(n => n + 1); }}>Tentar novamente</button>
    </> : grupos === null ? <p role="status">Consultando telefones compartilhados…</p> :
      grupos.length === 0 ? <p>Nenhum telefone compartilhado entre os clientes ativos da unidade.</p> :
      <><p>Um telefone compartilhado indica que os cadastros precisam de conferência.</p>
        {grupos.map(grupo => <details key={grupo.telefone_normalizado}>
          <summary>+{grupo.telefone_normalizado} · {grupo.clientes.length} cadastros
            {grupo.inclui_presencial_e_online && ' · Cadastro presencial e conta online'}</summary>
          <ul>{grupo.clientes.map(cliente => <li key={cliente.id}>
            <span>{cliente.nome} · {cliente.conta_ativada ? 'Conta online' : 'Cadastro presencial'}</span>
            <button type="button" onClick={() => selecionar(cliente.id)}>Ver cadastro de {cliente.nome}</button>
          </li>)}</ul>
        </details>)}
      </>}
  </section>;
}
