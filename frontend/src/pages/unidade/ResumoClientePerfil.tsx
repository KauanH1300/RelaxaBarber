import { useEffect, useState } from 'react';
import api from '../../services/api';
import { mensagemErro } from '../../services/erros';
import { descricaoEscopo } from '../../services/resumoCliente';
import type { ResumoCliente } from '../../services/resumoCliente';

export function ResumoClientePerfil({ clienteId, administrador }: { clienteId: string; administrador: boolean }) {
  const [resumo, setResumo] = useState<ResumoCliente | null>(null);
  const [erro, setErro] = useState('');
  useEffect(() => {
    let ativo = true;
    const endpoint = administrador ? 'resumo-financeiro' : 'resumo';
    api.get<ResumoCliente>(`/clientes/${clienteId}/${endpoint}`).then(({ data }) => {
      if (ativo) setResumo(data);
    }).catch((falha) => {
      if (ativo) setErro(mensagemErro(falha, 'Não foi possível consultar o resumo do cliente'));
    });
    return () => { ativo = false; };
  }, [clienteId, administrador]);
  return <section aria-label="Resumo do cliente">
    {erro ? <p role="alert">{erro}</p> : !resumo ? <p role="status">Carregando resumo...</p> : <>
      <p>{descricaoEscopo(resumo)}</p>
      <p>Atendimentos concluídos no escopo acima: {resumo.atendimentos_concluidos}</p>
      <details><summary>Detalhamento por filial</summary>
        <ul>{resumo.filiais.map((filial) => <li key={filial.filial_id}>
          {filial.filial_nome}: {filial.atendimentos_concluidos} atendimento(s) concluído(s)
        </li>)}</ul>
      </details>
      <p>Valores financeiros indisponíveis no momento.</p>
      {!administrador && <p>A consulta financeira é restrita ao administrador.</p>}
    </>}
  </section>;
}
