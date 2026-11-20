export function CompararEdicao({ linhas, confirmar }: {
  linhas: { id?: string; campo: string; atual: string; rascunho: string }[];
  confirmar: () => void;
}) {
  return <section aria-label="Comparação com a versão atual">
    <p role="status">Compare a versão atual com seu rascunho. Confirmar a revisão permite editar e salvar novamente.</p>
    <table><thead><tr><th>Campo</th><th>Atual</th><th>Seu rascunho</th></tr></thead>
      <tbody>{linhas.map(l => <tr key={l.id ?? l.campo}><th scope="row">{l.campo}</th><td>{l.atual}</td><td>{l.rascunho}</td></tr>)}</tbody>
    </table>
    <button type="button" onClick={confirmar}>Usar versão atual para revisar meu rascunho</button>
  </section>;
}
