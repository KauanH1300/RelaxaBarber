import { useEffect, useId, useRef, useState } from 'react';
import { chaveRascunhoCliente, clienteParaDados, consultarCliente, conferirCadastroCliente, dadosClienteAlterados, dadosClienteVazios, dadosRascunhoAlterados, LIMITE_PREFERENCIAS, erroCliente, lerRascunhoCliente, prepararCliente, salvarCliente, serializarRascunhoCliente } from '../../services/clientes';
import type { Cliente, DadosCliente } from '../../services/clientes';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { diaLocal } from '../gerencial/formatacao';
import { escritaIncerta } from '../../services/erros';
import { useProtecaoCliente } from './useProtecaoCliente';
import { useConferencia } from '../../services/useConferencia';

export function FormCliente({ id, usuarioId, habilitado = true, aoCancelar, aoSalvar }: {
  id?: string; usuarioId: string; habilitado?: boolean; aoCancelar: () => void; aoSalvar: (cliente: Cliente) => void;
}) {
  const [contexto] = useState(contextoAtual);
  const chave = chaveRascunhoCliente(usuarioId, contexto.filialId ?? '', id);
  const [rascunho] = useState(() => {
    try { return lerRascunhoCliente(sessionStorage.getItem(chave)); } catch { return null; }
  });
  const [dados, setDados] = useState<DadosCliente>(() => ({ ...dadosClienteVazios(), ...(!id ? rascunho?.dados : undefined) }));
  const [base, setBase] = useState(dadosClienteVazios);
  const [carregando, setCarregando] = useState(!!id);
  const [erroCarga, setErroCarga] = useState('');
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [incerto, setIncerto] = useState(!id && !!rascunho?.incerto);
  const [aviso, setAviso] = useState(!id && rascunho ? 'Rascunho recuperado nesta sessão do navegador.' : '');
  const [tentativa, setTentativa] = useState(0);
  const enviando = useRef(false);
  const chaveCadastro = useRef(rascunho?.chaveCadastro);
  const edicaoEnviada = useRef<ReturnType<typeof prepararCliente> | null>(null);
  const { conferir, consultando, aviso: avisoConferencia } = useConferencia();
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
      setBase(atual); setDados({ ...atual, ...rascunho?.dados }); setIncerto(!!rascunho?.incerto); setErroCarga('');
      if (rascunho) setAviso(dadosRascunhoAlterados(atual, rascunho.base)
        ? 'O cadastro mudou desde o rascunho. Confira os dados atuais antes de salvar seus ajustes.'
        : 'Rascunho recuperado nesta sessão do navegador.');
    }).catch((falha: unknown) => {
      if (!controller.signal.aborted && contextoValido(contexto)) setErroCarga(erroCliente(falha, 'Não foi possível carregar o cliente'));
    }).finally(() => { if (!controller.signal.aborted && contextoValido(contexto)) setCarregando(false); });
    return () => controller.abort();
  }, [id, contexto, tentativa, rascunho]);

  function guardar(novos: DadosCliente, resultadoIncerto = incerto) {
    try {
      if (dadosRascunhoAlterados(novos, base) || resultadoIncerto) sessionStorage.setItem(chave,
        serializarRascunhoCliente(novos, base, resultadoIncerto, Date.now(), resultadoIncerto ? chaveCadastro.current : undefined));
      else sessionStorage.removeItem(chave);
    } catch { setAviso('O navegador não permitiu guardar o rascunho. Salve antes de sair.'); }
  }
  function alterar(novos: DadosCliente) { setDados(novos); setErro(''); guardar(novos); }
  function cancelar() {
    if (enviando.current || consultando) return;
    if (!incerto && pendente && !window.confirm('Descartar as alterações não salvas deste cliente?')) return;
    if (!incerto) {
      try { sessionStorage.removeItem(chave); } catch { /* Armazenamento opcional. */ }
    }
    aoCancelar();
  }
  function confirmado(cliente: Cliente) {
    try { sessionStorage.removeItem(chave); } catch { /* Armazenamento opcional. */ }
    aoSalvar(cliente);
  }
  async function conferirCliente() {
    const filial = contexto.filialId;
    const operacao = chaveCadastro.current;
    if (!filial || !contextoValido(contexto)) return;
    await conferir(async () => id ? consultarCliente(id, filial)
      : operacao ? conferirCadastroCliente(operacao, filial) : undefined, atual => {
      if (!atual?.id) return false;
      if (id) {
        const esperado = edicaoEnviada.current;
        if (!esperado || atual.id !== id || atual.nome !== esperado.nome || atual.telefone !== esperado.telefone ||
          (atual.email ?? null) !== esperado.email || (atual.data_nascimento ?? null) !== esperado.data_nascimento ||
          (atual.preferencias ?? null) !== esperado.preferencias) return false;
      }
      confirmado(atual);
      return true;
    });
  }
  async function enviar(event: React.FormEvent) {
    event.preventDefault();
    if (!habilitado || enviando.current || carregando || erroCarga || incerto) return;
    if (!contextoValido(contexto) || !contexto.filialId) { setErro('Selecione novamente uma filial autorizada.'); return; }
    try {
      const payload = prepararCliente(dados);
      if (id) edicaoEnviada.current = payload;
      else chaveCadastro.current = crypto.randomUUID();
    } catch (falha) { setErro((falha as Error).message); return; }
    enviando.current = true; setSalvando(true); setErro('');
    // Uma saída antes da resposta exige conferir a escrita antes de repeti-la.
    guardar(dados, true);
    try {
      const cliente = await salvarCliente(dados, contexto.filialId, id, chaveCadastro.current);
      if (montado.current && contextoValido(contexto)) confirmado(cliente);
    } catch (falha: unknown) {
      if (!montado.current || !contextoValido(contexto)) return;
      const resultadoIncerto = escritaIncerta(falha);
      setIncerto(resultadoIncerto); guardar(dados, resultadoIncerto);
      if (!resultadoIncerto) setErro(erroCliente(falha, 'Não foi possível salvar o cliente'));
    } finally { enviando.current = false; if (montado.current) setSalvando(false); }
  }
  return <form className="cliente-form" onSubmit={enviar} aria-labelledby={tituloId} aria-busy={carregando || salvando}>
    <h2 id={tituloId}>{id ? 'Editar cliente' : 'Novo cliente'}</h2>
    {id && <p>O cadastro é compartilhado: alterações também aparecem nas outras unidades vinculadas.</p>}
    {aviso && <p role="status">{aviso}</p>}
    {incerto && <><p role="status">Há um salvamento a conferir. O resultado continua incerto.</p>
      <button type="button" disabled={consultando} onClick={() => void conferirCliente()}>{consultando ? 'Conferindo…' : 'Conferir resultado'}</button>
      {avisoConferencia && <p role="status">{avisoConferencia}</p>}</>}
    {pendente && !incerto && !salvando && <p className="cliente-pendente">Alterações não salvas</p>}
    {carregando && <p role="status">Carregando cliente...</p>}
    {erroCarga && <><p role="alert">{erroCarga}</p><button type="button" onClick={() => { setCarregando(true); setErroCarga(''); setTentativa((n) => n + 1); }}>Tentar novamente</button></>}
    {erro && <p role="alert">{erro}</p>}
    <fieldset disabled={!habilitado || carregando || !!erroCarga || salvando || incerto}>
      <label>Nome *<input ref={nomeInput} name="nome" autoComplete="name" required maxLength={150} value={dados.nome} onChange={(e) => alterar({ ...dados, nome: e.target.value })} /></label>
      <label>Telefone *<input name="telefone" type="tel" autoComplete="tel" required maxLength={20} value={dados.telefone} onChange={(e) => alterar({ ...dados, telefone: e.target.value })} /></label>
      <label>E-mail (opcional)<input name="email" type="email" autoComplete="email" maxLength={254} value={dados.email} onChange={(e) => alterar({ ...dados, email: e.target.value })} /></label>
      <label>Data de nascimento (opcional)<input name="data_nascimento" type="date" max={diaLocal()} value={dados.data_nascimento} onChange={(e) => alterar({ ...dados, data_nascimento: e.target.value })} /></label>
      <label>Observações e preferências (opcional)<textarea name="preferencias" rows={4} maxLength={LIMITE_PREFERENCIAS} value={dados.preferencias} onChange={(e) => alterar({ ...dados, preferencias: e.target.value })} /></label>
    </fieldset>
    {id && rascunho && !carregando && !erroCarga && <details><summary>Dados atuais no servidor</summary><dl><dt>Nome</dt><dd>{base.nome}</dd><dt>Telefone</dt><dd>{base.telefone}</dd><dt>E-mail</dt><dd>{base.email || 'Não informado'}</dd></dl></details>}
    {salvando && <p role="status">Salvando cliente...</p>}
    <div className="clientes-acoes">
      <button type="submit" disabled={!habilitado || carregando || !!erroCarga || salvando || incerto || (!!id && !pendente)}>{salvando ? 'Salvando...' : 'Salvar cliente'}</button>
      <button type="button" disabled={salvando || consultando} onClick={cancelar}>{incerto ? 'Fechar e manter pendência' : 'Cancelar'}</button>
    </div>
    <p className="cliente-nota">Rascunhos de contato expiram em até 8 horas nesta sessão. Data de nascimento e preferências são guardadas ao salvar o cadastro.</p>
  </form>;
}
