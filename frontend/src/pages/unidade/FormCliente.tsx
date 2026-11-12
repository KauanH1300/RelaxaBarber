import { useEffect, useId, useRef, useState } from 'react';
import { chaveRascunhoCliente, clienteParaDados, consultarCliente, dadosClienteAlterados, dadosClienteVazios, erroCliente, lerRascunhoCliente, prepararCliente, salvarCliente, serializarRascunhoCliente } from '../../services/clientes';
import type { Cliente, DadosCliente } from '../../services/clientes';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { escritaIncerta } from '../../services/erros';
import { useProtecaoCliente } from './useProtecaoCliente';

export function FormCliente({ id, usuarioId, habilitado = true, aoCancelar, aoSalvar }: {
  id?: string; usuarioId: string; habilitado?: boolean; aoCancelar: () => void; aoSalvar: (cliente: Cliente) => void;
}) {
  const [contexto] = useState(contextoAtual);
  const chave = chaveRascunhoCliente(usuarioId, contexto.filialId ?? '', id);
  const [rascunho] = useState(() => {
    try { return lerRascunhoCliente(sessionStorage.getItem(chave)); } catch { return null; }
  });
  const [dados, setDados] = useState<DadosCliente>(() => !id && rascunho ? rascunho.dados : dadosClienteVazios());
  const [base, setBase] = useState(dadosClienteVazios);
  const [carregando, setCarregando] = useState(!!id);
  const [erroCarga, setErroCarga] = useState('');
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [incerto, setIncerto] = useState(!id && !!rascunho?.incerto);
  const [aviso, setAviso] = useState(!id && rascunho ? 'Rascunho recuperado nesta sessão do navegador.' : '');
  const [tentativa, setTentativa] = useState(0);
  const enviando = useRef(false);
  const montado = useRef(false);
  const nomeInput = useRef<HTMLInputElement>(null);
  const tituloId = useId();
  const pendente = dadosClienteAlterados(dados, base);
  useProtecaoCliente(pendente || salvando || incerto, contexto.filialId);
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => { if (!carregando && !erroCarga) nomeInput.current?.focus(); }, [carregando, erroCarga]);

  useEffect(() => {
    if (!id || !contexto.filialId) return;
    const controller = new AbortController();
    consultarCliente(id, contexto.filialId, controller.signal).then((cliente) => {
      if (controller.signal.aborted || !contextoValido(contexto)) return;
      const atual = clienteParaDados(cliente);
      setBase(atual); setDados(rascunho?.dados ?? atual); setIncerto(!!rascunho?.incerto); setErroCarga('');
      if (rascunho) setAviso(dadosClienteAlterados(atual, rascunho.base)
        ? 'O cadastro mudou desde o rascunho. Confira os dados atuais antes de salvar seus ajustes.'
        : 'Rascunho recuperado nesta sessão do navegador.');
    }).catch((falha: unknown) => {
      if (!controller.signal.aborted && contextoValido(contexto)) setErroCarga(erroCliente(falha, 'Não foi possível carregar o cliente'));
    }).finally(() => { if (!controller.signal.aborted && contextoValido(contexto)) setCarregando(false); });
    return () => controller.abort();
  }, [id, contexto, tentativa, rascunho]);

  function guardar(novos: DadosCliente, resultadoIncerto = incerto) {
    try {
      if (dadosClienteAlterados(novos, base) || resultadoIncerto) sessionStorage.setItem(chave, serializarRascunhoCliente(novos, base, resultadoIncerto));
      else sessionStorage.removeItem(chave);
    } catch { setAviso('O navegador não permitiu guardar o rascunho. Salve antes de sair.'); }
  }
  function alterar(novos: DadosCliente) { setDados(novos); setErro(''); guardar(novos); }
  function cancelar(descartarIncerto = false) {
    if (enviando.current) return;
    const mensagem = incerto && descartarIncerto
      ? 'Já conferiu se a operação foi salva? Descartar este rascunho permitirá uma nova tentativa.'
      : 'Descartar as alterações não salvas deste cliente?';
    if (((!incerto && pendente) || (incerto && descartarIncerto)) && !window.confirm(mensagem)) return;
    if (!incerto || descartarIncerto) {
      try { sessionStorage.removeItem(chave); } catch { /* Armazenamento opcional. */ }
    }
    aoCancelar();
  }
  async function enviar(event: React.FormEvent) {
    event.preventDefault();
    if (!habilitado || enviando.current || carregando || erroCarga || incerto) return;
    if (!contextoValido(contexto) || !contexto.filialId) { setErro('Selecione novamente uma filial autorizada.'); return; }
    try { prepararCliente(dados); } catch (falha) { setErro((falha as Error).message); return; }
    enviando.current = true; setSalvando(true); setErro('');
    // Uma saída antes da resposta exige conferir a escrita antes de repeti-la.
    guardar(dados, true);
    try {
      const cliente = await salvarCliente(dados, contexto.filialId, id);
      try { sessionStorage.removeItem(chave); } catch { /* Armazenamento opcional. */ }
      if (montado.current && contextoValido(contexto)) aoSalvar(cliente);
    } catch (falha: unknown) {
      if (!montado.current || !contextoValido(contexto)) return;
      const resultadoIncerto = escritaIncerta(falha);
      setIncerto(resultadoIncerto); guardar(dados, resultadoIncerto);
      setErro(erroCliente(falha, 'Não foi possível salvar o cliente') + (resultadoIncerto ? ' Feche o formulário e atualize a lista antes de tentar novamente.' : ''));
    } finally { enviando.current = false; if (montado.current) setSalvando(false); }
  }
  return <form className="cliente-form" onSubmit={enviar} aria-labelledby={tituloId} aria-busy={carregando || salvando}>
    <h2 id={tituloId}>{id ? 'Editar cliente' : 'Novo cliente'}</h2>
    {id && <p>O cadastro é compartilhado: alterações também aparecem nas outras unidades vinculadas.</p>}
    {aviso && <p role="status">{aviso}</p>}
    {incerto && <p role="alert">Há um salvamento a conferir. Consulte a lista ou o cadastro antes de repetir a operação.</p>}
    {pendente && <p className="cliente-pendente">Alterações não salvas</p>}
    {carregando && <p role="status">Carregando cliente...</p>}
    {erroCarga && <><p role="alert">{erroCarga}</p><button type="button" onClick={() => { setCarregando(true); setErroCarga(''); setTentativa((n) => n + 1); }}>Tentar novamente</button></>}
    {erro && <p role="alert">{erro}</p>}
    <fieldset disabled={!habilitado || carregando || !!erroCarga || salvando || incerto}>
      <label>Nome *<input ref={nomeInput} name="nome" autoComplete="name" required maxLength={150} value={dados.nome} onChange={(e) => alterar({ ...dados, nome: e.target.value })} /></label>
      <label>Telefone *<input name="telefone" type="tel" autoComplete="tel" required maxLength={20} value={dados.telefone} onChange={(e) => alterar({ ...dados, telefone: e.target.value })} /></label>
      <label>E-mail (opcional)<input name="email" type="email" autoComplete="email" maxLength={254} value={dados.email} onChange={(e) => alterar({ ...dados, email: e.target.value })} /></label>
    </fieldset>
    {id && rascunho && !carregando && !erroCarga && <details><summary>Dados atuais no servidor</summary><dl><dt>Nome</dt><dd>{base.nome}</dd><dt>Telefone</dt><dd>{base.telefone}</dd><dt>E-mail</dt><dd>{base.email || 'Não informado'}</dd></dl></details>}
    {salvando && <p role="status">Salvando cliente...</p>}
    <div className="clientes-acoes">
      <button type="submit" disabled={!habilitado || carregando || !!erroCarga || salvando || incerto || (!!id && !pendente)}>{salvando ? 'Salvando...' : 'Salvar cliente'}</button>
      <button type="button" disabled={salvando} onClick={() => cancelar()}>{incerto ? 'Fechar e conferir lista' : 'Cancelar'}</button>
      {incerto && <button type="button" disabled={salvando} onClick={() => cancelar(true)}>Descartar rascunho após conferência</button>}
    </div>
    <p className="cliente-nota">Rascunhos expiram em até 8 horas e ficam apenas nesta sessão do navegador. Não são enviados até salvar.</p>
  </form>;
}
