import { useEffect, useState } from 'react';
import axios from 'axios';
import { useUsuario } from '../../services/usuario';
import { useFilial } from '../../services/filialEstado';
import { ResumoClientePerfil } from './ResumoClientePerfil';
import { erroCliente, listarClientes, podeGerenciarClientes } from '../../services/clientes';
import type { Cliente } from '../../services/clientes';
import { FormCliente } from './FormCliente';
import { DetalheCliente } from './DetalheCliente';
import './clientes.css';

export function ClientesUnidade() {
  const usuario = useUsuario();
  const { filialId } = useFilial();
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [formulario, setFormulario] = useState<{ id?: string } | null>(null);
  const [sucesso, setSucesso] = useState('');
  const [registros, setRegistros] = useState<Cliente[]>([]);
  const [erro, setErro] = useState('');
  const [carregando, setCarregando] = useState(true);
  const [busca, setBusca] = useState('');
  const [filtro, setFiltro] = useState('');
  const [tentativa, setTentativa] = useState(0);
  const [versao, setVersao] = useState(0);
  const habilitado = podeGerenciarClientes(usuario);
  useEffect(() => {
    const controller = new AbortController();
    listarClientes(filtro, controller.signal).then((data) => {
      if (!controller.signal.aborted) { setRegistros(data); setErro(''); }
    }).catch((falha) => {
      if (!controller.signal.aborted && !axios.isCancel(falha)) { setRegistros([]); setErro(erroCliente(falha, 'Não foi possível carregar os clientes da unidade')); }
    }).finally(() => { if (!controller.signal.aborted) setCarregando(false); });
    return () => controller.abort();
  }, [filtro, tentativa]);
  function recarregar(novoFiltro = filtro) { setCarregando(true); setErro(''); setRegistros([]); setFiltro(novoFiltro); setTentativa((n) => n + 1); }
  function salvo(cliente: Cliente) {
    setSucesso(formulario?.id ? 'Cliente atualizado com sucesso.' : 'Cliente cadastrado com sucesso.');
    setFormulario(null); setVersao((n) => n + 1);
    if (selecionado === cliente.id) setSelecionado(cliente.id);
    recarregar();
  }
  return <section className="clientes-unidade" aria-labelledby="clientes-titulo">
    <header className="clientes-cabecalho"><div><p className="cliente-nota">Gestão da unidade</p><h1 id="clientes-titulo">Clientes da unidade</h1><p>Cadastros vinculados à filial ativa.</p></div>
      {habilitado && <button type="button" disabled={!!formulario} onClick={() => { setSucesso(''); setFormulario({}); }}>Novo cliente</button>}
    </header>
    {sucesso && <p role="status">{sucesso}{filtro && ' A lista continua filtrada pela busca atual.'}</p>}
    {formulario && <FormCliente key={formulario.id ?? 'novo'} usuarioId={usuario.id} habilitado={habilitado} id={formulario.id} aoSalvar={salvo} aoCancelar={() => { setFormulario(null); recarregar(); }} />}
    <form className="clientes-busca" role="search" onSubmit={(event) => { event.preventDefault(); recarregar(busca.trim()); }}>
      <label htmlFor="busca-clientes">Buscar por nome ou telefone</label>
      <div><input id="busca-clientes" type="search" maxLength={150} value={busca} onChange={(event) => setBusca(event.target.value)} placeholder="Nome ou telefone nesta unidade" />
        <button type="submit">Buscar</button><button type="button" onClick={() => { setBusca(''); recarregar(''); }}>Limpar busca</button>
      </div>
    </form>
    <div className="clientes-lista" aria-busy={carregando}>
      {carregando && <p role="status">Carregando clientes...</p>}
      {erro && <p role="alert">{erro}</p>}
      <button type="button" disabled={carregando} onClick={() => recarregar()}>{erro ? 'Tentar novamente' : 'Atualizar clientes'}</button>
      {!carregando && !erro && <p role="status">{registros.length ? `${registros.length} cliente(s) encontrado(s).` : filtro ? 'Nenhum cliente encontrado nesta unidade para essa busca.' : 'Nenhum cliente vinculado a esta unidade.'}</p>}
      <ul aria-label="Clientes encontrados">{registros.map((cliente) => <li key={cliente.id}>
        <div><strong>{cliente.nome}</strong><p>{cliente.telefone}</p></div>
        <div className="clientes-acoes"><button type="button" aria-label={`Ver cadastro de ${cliente.nome}`} onClick={() => setSelecionado(cliente.id)}>Ver cadastro</button>
          {habilitado && <button type="button" disabled={!!formulario} aria-label={`Editar ${cliente.nome}`} onClick={() => { setSucesso(''); setFormulario({ id: cliente.id }); }}>Editar</button>}
        </div>
      </li>)}</ul>
    </div>
    {selecionado && filialId && <section className="cliente-perfil" aria-label="Perfil do cliente">
      <button type="button" onClick={() => { setSelecionado(null); document.querySelector<HTMLInputElement>('#busca-clientes')?.focus(); }}>Fechar perfil</button>
      <DetalheCliente key={`${selecionado}:${versao}`} id={selecionado} filialId={filialId} />
      <ResumoClientePerfil key={`${selecionado}:${usuario.perfil}:${versao}`} clienteId={selecionado} administrador={usuario.perfil === 'admin'} />
    </section>}
  </section>;
}
