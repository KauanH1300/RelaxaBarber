import { useEffect, useId, useRef, useState } from 'react';
import axios from 'axios';
import { consultarCliente, erroCliente } from '../../services/clientes';
import type { Cliente } from '../../services/clientes';

export function DadosCadastraisCliente({ cliente }: { cliente: Cliente }) {
  return <dl className="cliente-dados"><dt>Nome</dt><dd>{cliente.nome}</dd><dt>Telefone</dt><dd>{cliente.telefone}</dd>
    <dt>E-mail</dt><dd>{cliente.email || 'Não informado'}</dd><dt>Situação</dt><dd>{cliente.ativo ? 'Ativo' : 'Inativo'}</dd></dl>;
}
export function DetalheCliente({ id, filialId }: { id: string; filialId: string }) {
  const [cliente, setCliente] = useState<Cliente | null>(null);
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [tentativa, setTentativa] = useState(0);
  const tituloId = useId();
  const titulo = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    consultarCliente(id, filialId, controller.signal).then((data) => {
      if (!controller.signal.aborted) { setCliente(data); setErro(''); }
    }).catch((falha) => {
      if (!controller.signal.aborted && !axios.isCancel(falha)) { setErro(erroCliente(falha, 'Não foi possível consultar o cadastro')); setCliente(null); }
    }).finally(() => { if (!controller.signal.aborted) setCarregando(false); });
    return () => controller.abort();
  }, [id, filialId, tentativa]);
  useEffect(() => { titulo.current?.focus(); }, []);
  return <section className="cliente-detalhe" aria-labelledby={tituloId} aria-busy={carregando}>
    <h3 id={tituloId} ref={titulo} tabIndex={-1}>Dados cadastrais</h3>
    {carregando ? <p role="status">Carregando cadastro...</p> : erro ? <><p role="alert">{erro}</p><button type="button" onClick={() => { setCarregando(true); setTentativa((n) => n + 1); }}>Tentar consultar novamente</button></> : cliente && <DadosCadastraisCliente cliente={cliente} />}
  </section>;
}
