import { useEffect, useRef, useState } from 'react';
import { useUsuario, nomesPerfil } from '../../services/usuario';
import { useFilial } from '../../services/filialEstado';
import type { Filial } from '../../services/filialAtiva';
import { atualizarFuncionario, cadastrarFuncionario, conferirCadastroFuncionario, definirVinculo, listarFuncionarios, listarVinculos, podeGerenciarFuncionarios } from '../../services/funcionarios';
import type { DadosFuncionario, Funcionario, VinculoFuncionario } from '../../services/funcionarios';
import type { PerfilAgenda } from '../../services/permissoesAgenda';
import { escritaIncerta, mensagemErro } from '../../services/erros';
import './funcionarios.css';
import { Jornada } from './Jornada';
import { RestricoesServicos } from './RestricoesServicos';
import { ComissoesFuncionario } from './ComissoesFuncionario';
import { useConferencia } from '../../services/useConferencia';

export function FormFuncionario({ funcionario, filiais, proprio, aoSalvar, aoCancelar }: {
  funcionario?: Funcionario; filiais: Filial[]; proprio: boolean; aoSalvar: () => void; aoCancelar: () => void;
}) {
  const operador = useUsuario();
  const storage = `relaxabarber:funcionario:cadastro:${operador.id}`;
  const [dados, setDados] = useState<DadosFuncionario>({ nome: funcionario?.nome ?? '', email: funcionario?.email ?? '', telefone: funcionario?.telefone ?? '', perfil: funcionario?.perfil ?? 'barbeiro', ativo: funcionario?.ativo ?? true });
  const [senha, setSenha] = useState('');
  const [ids, setIds] = useState<string[]>([]);
  const [erro, setErro] = useState('');
  const [salvando, setSalvando] = useState(false);
  const [chaveInicial] = useState(() => {
    try { return !funcionario ? sessionStorage.getItem(storage) : null; } catch { return null; }
  });
  const [incerto, setIncerto] = useState(!!chaveInicial);
  const chaveCadastro = useRef(chaveInicial ?? undefined);
  const { conferir, consultando, aviso } = useConferencia();
  const trava = useRef(false);
  const preparar = () => ({ ...dados, nome: dados.nome.trim(), email: dados.email.trim().toLowerCase(), telefone: dados.telefone?.trim() || null });
  function confirmar() {
    if (!funcionario) { try { sessionStorage.removeItem(storage); } catch { /* A chave continua consultável. */ } }
    aoSalvar();
  }
  async function conferirFuncionario() {
    const esperado = preparar();
    const chave = chaveCadastro.current;
    await conferir(async () => funcionario
      ? (await listarFuncionarios()).find(item => item.id === funcionario.id)
      : chave ? conferirCadastroFuncionario(chave) : undefined, atual => {
      if (!atual || (funcionario && (atual.nome !== esperado.nome || atual.email !== esperado.email ||
          atual.telefone !== esperado.telefone || atual.perfil !== esperado.perfil || atual.ativo !== esperado.ativo))) return false;
      confirmar();
      return true;
    });
  }
  async function salvar(event: React.FormEvent) {
    event.preventDefault();
    if (trava.current || incerto) return;
    if (!funcionario && !ids.length) { setErro('Selecione ao menos uma filial.'); return; }
    if (funcionario?.ativo && !dados.ativo && !window.confirm(`Inativar ${funcionario.nome}? O histórico será preservado.`)) return;
    trava.current = true; setSalvando(true); setErro('');
    try {
      const payload = preparar();
      if (funcionario) await atualizarFuncionario(funcionario.id, payload);
      else {
        chaveCadastro.current = crypto.randomUUID();
        sessionStorage.setItem(storage, chaveCadastro.current);
        await cadastrarFuncionario(payload, senha, ids, chaveCadastro.current);
      }
      setSenha(''); confirmar();
    } catch (falha) {
      if (escritaIncerta(falha)) { setIncerto(true); setSenha(''); }
      else {
        if (!funcionario) { try { sessionStorage.removeItem(storage); } catch { /* Nenhum reenvio automático. */ } }
        setErro(mensagemErro(falha, 'Não foi possível salvar o funcionário'));
      }
    } finally { trava.current = false; setSalvando(false); }
  }
  return <form className="funcionario-form" onSubmit={salvar} aria-label={funcionario ? 'Editar funcionário' : 'Cadastrar funcionário'} aria-busy={salvando}>
    <h2>{funcionario ? 'Editar funcionário' : 'Novo funcionário'}</h2>
    {erro && <p role="alert">{erro}</p>}
    {incerto && <><p role="status">Resultado não confirmado. Confira o cadastro sem reenviar os dados.</p>
      <button type="button" disabled={consultando} onClick={() => void conferirFuncionario()}>{consultando ? 'Conferindo…' : 'Conferir resultado'}</button>
      {aviso && <p role="status">{aviso}</p>}</>}
    <fieldset disabled={salvando || incerto}>
      <label>Nome<input required minLength={2} maxLength={150} autoComplete="name" value={dados.nome} onChange={e => setDados({ ...dados, nome: e.target.value })} /></label>
      <label>E-mail<input required type="email" maxLength={255} autoComplete="email" value={dados.email} onChange={e => setDados({ ...dados, email: e.target.value })} /></label>
      <label>Telefone<input type="tel" maxLength={20} autoComplete="tel" value={dados.telefone ?? ''} onChange={e => setDados({ ...dados, telefone: e.target.value })} /></label>
      <label>Perfil<select disabled={proprio} value={dados.perfil} onChange={e => setDados({ ...dados, perfil: e.target.value as PerfilAgenda })}>{Object.entries(nomesPerfil).map(([id, nome]) => <option key={id} value={id}>{nome}</option>)}</select></label>
      {funcionario ? <label><input type="checkbox" disabled={proprio} checked={dados.ativo} onChange={e => setDados({ ...dados, ativo: e.target.checked })} />Funcionário ativo</label> : <>
        <label>Senha inicial<input required type="password" minLength={8} maxLength={128} autoComplete="new-password" value={senha} onChange={e => setSenha(e.target.value)} /></label>
        <fieldset><legend>Filiais do funcionário</legend>{filiais.map(f => <label key={f.id}><input type="checkbox" checked={ids.includes(f.id)} onChange={e => setIds(e.target.checked ? [...ids, f.id] : ids.filter(id => id !== f.id))} />{f.nome}</label>)}</fieldset>
      </>}
      {proprio && <p>Seu próprio perfil administrativo e sua atividade não podem ser removidos.</p>}
      <button type="submit">{salvando ? 'Salvando…' : 'Salvar funcionário'}</button>
    </fieldset>
    <button type="button" disabled={salvando || consultando} onClick={aoCancelar}>Fechar formulário e atualizar lista</button>
  </form>;
}

function Vinculos({ funcionario, filiais }: { funcionario: Funcionario; filiais: Filial[] }) {
  const [registros, setRegistros] = useState<Record<string, VinculoFuncionario[]>>({});
  const [erro, setErro] = useState('');
  const [mensagem, setMensagem] = useState('');
  const [ocupado, setOcupado] = useState(true);
  const [versao, setVersao] = useState(0);
  const [incerto, setIncerto] = useState(false);
  const trava = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all(filiais.map(async f => [f.id, await listarVinculos(f.id, controller.signal)] as const)).then(rows => {
      if (!controller.signal.aborted) { setRegistros(Object.fromEntries(rows)); setErro(''); setIncerto(false); }
    }).catch(falha => { if (!controller.signal.aborted) setErro(mensagemErro(falha, 'Não foi possível consultar os vínculos')); })
      .finally(() => { if (!controller.signal.aborted) setOcupado(false); });
    return () => controller.abort();
  }, [filiais, versao]);
  function consultar() { setOcupado(true); setRegistros({}); setVersao(n => n + 1); }
  async function alterar(filial: Filial, ativo: boolean) {
    if (trava.current || ocupado || incerto) return;
    if (!ativo && !window.confirm(`Desativar o vínculo com ${filial.nome}?`)) return;
    trava.current = true; setOcupado(true); setErro(''); setMensagem('');
    try { await definirVinculo(filial.id, funcionario.id, ativo); setMensagem('Vínculo atualizado.'); consultar(); }
    catch (falha) { setErro(mensagemErro(falha, 'Não foi possível atualizar o vínculo')); if (escritaIncerta(falha)) setIncerto(true); setOcupado(false); }
    finally { trava.current = false; }
  }
  return <section aria-label="Vínculos com filiais" aria-busy={ocupado}><h3>Filiais de {funcionario.nome}</h3>
    <p>Alterações de vínculo são salvas individualmente. Reservas futuras podem impedir a desativação.</p>
    {erro && <p role="alert">{erro}</p>}{mensagem && <p role="status">{mensagem}</p>}
    {incerto && <p role="status">Resultado não confirmado. Consulte os vínculos antes de continuar.</p>}
    <button type="button" disabled={ocupado} onClick={consultar}>Consultar vínculos</button>
    {ocupado && <p role="status">Consultando ou atualizando vínculos…</p>}
    <ul>{filiais.map(f => { const ativo = registros[f.id]?.some(v => v.usuario_id === funcionario.id && v.ativo) ?? false;
      return <li key={f.id}><span>{f.nome} — {registros[f.id] ? ativo ? 'Vínculo ativo' : 'Sem vínculo ativo' : 'Não consultado'}</span>
        <button type="button" disabled={ocupado || incerto || !registros[f.id] || (!ativo && !funcionario.ativo)} onClick={() => void alterar(f, !ativo)}>{ativo ? 'Desativar vínculo' : 'Ativar vínculo'}</button></li>;
    })}</ul>
  </section>;
}

export function Funcionarios() {
  const usuario = useUsuario();
  if (!podeGerenciarFuncionarios(usuario)) return <p role="alert">Somente administradores podem gerenciar funcionários.</p>;
  return <GestaoFuncionarios />;
}

function GestaoFuncionarios() {
  const usuario = useUsuario(); const { filiais } = useFilial();
  const [itens, setItens] = useState<Funcionario[]>([]);
  const [erro, setErro] = useState(''); const [ocupado, setOcupado] = useState(true);
  const [versao, setVersao] = useState(0); const [busca, setBusca] = useState(''); const [estado, setEstado] = useState('todos');
  const [formulario, setFormulario] = useState<{ funcionario?: Funcionario } | null>(null);
  const [vinculos, setVinculos] = useState<Funcionario | null>(null); const [sucesso, setSucesso] = useState('');
  const [jornada, setJornada] = useState<Funcionario | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    listarFuncionarios(controller.signal).then(dados => { if (!controller.signal.aborted) { setItens(dados); setErro(''); } })
      .catch(falha => { if (!controller.signal.aborted) setErro(mensagemErro(falha, 'Não foi possível carregar funcionários')); })
      .finally(() => { if (!controller.signal.aborted) setOcupado(false); });
    return () => controller.abort();
  }, [versao]);
  function atualizarLista() { setOcupado(true); setItens([]); setVersao(n => n + 1); }
  function fechar() { setFormulario(null); setVinculos(null); atualizarLista(); }
  const filtrados = itens.filter(f => `${f.nome} ${f.email}`.toLocaleLowerCase().includes(busca.toLocaleLowerCase()) && (estado === 'todos' || f.ativo === (estado === 'ativos')));
  return <section className="funcionarios" aria-labelledby="funcionarios-titulo"><header><h1 id="funcionarios-titulo">Funcionários</h1>
    <button disabled={!!formulario || !!vinculos || ocupado || !filiais.length} onClick={() => { setSucesso(''); setFormulario({}); }}>Novo funcionário</button></header>
    {sucesso && <p role="status">{sucesso}</p>}
    {jornada && <><h2>Jornada de {jornada.nome}</h2><button onClick={() => setJornada(null)}>Fechar jornada</button><Jornada barbeiroId={jornada.id} /></>}
    {formulario && <><FormFuncionario key={formulario.funcionario?.id ?? 'novo'} funcionario={formulario.funcionario} filiais={filiais} proprio={formulario.funcionario?.id === usuario.id} aoCancelar={fechar} aoSalvar={() => { fechar(); setSucesso('Funcionário salvo com sucesso.'); }} />
      {formulario.funcionario?.ativo && ['barbeiro', 'barbeiro_chefe'].includes(formulario.funcionario.perfil) && <><RestricoesServicos barbeiroId={formulario.funcionario.id} /><ComissoesFuncionario profissionalId={formulario.funcionario.id} /></>}</>}
    {vinculos && <><button onClick={fechar}>Fechar vínculos</button><Vinculos key={`${vinculos.id}:${filiais.map(f => f.id).join(':')}`} funcionario={vinculos} filiais={filiais} /></>}
    <div className="funcionarios-filtros"><label>Buscar nome ou e-mail<input type="search" value={busca} onChange={e => setBusca(e.target.value)} /></label>
      <label>Situação<select value={estado} onChange={e => setEstado(e.target.value)}><option value="todos">Todos</option><option value="ativos">Ativos</option><option value="inativos">Inativos</option></select></label>
      <button disabled={ocupado || !!formulario || !!vinculos} onClick={atualizarLista}>Atualizar lista</button></div>
    {erro && <p role="alert">{erro}</p>}{ocupado && <p role="status">Carregando funcionários…</p>}
    {!ocupado && !erro && <p role="status">{filtrados.length} funcionário(s) encontrado(s).</p>}
    <div className="funcionarios-tabela" tabIndex={0} role="region" aria-label="Lista de funcionários" aria-busy={ocupado}><table><thead><tr><th scope="col">Nome</th><th scope="col">Contato</th><th scope="col">Perfil</th><th scope="col">Situação</th><th scope="col">Ações</th></tr></thead><tbody>
      {filtrados.map(f => <tr key={f.id}><th scope="row">{f.nome}</th><td>{f.email}<br />{f.telefone}</td><td>{nomesPerfil[f.perfil]}</td><td>{f.ativo ? 'Ativo' : 'Inativo'}</td><td>
        <button disabled={!!formulario || !!vinculos} aria-label={`Editar ${f.nome}`} onClick={() => { setSucesso(''); setFormulario({ funcionario: f }); }}>Editar / atividade</button>
        <button disabled={!!formulario || !!vinculos} aria-label={`Filiais de ${f.nome}`} onClick={() => setVinculos(f)}>Filiais</button>
        {f.ativo && ['barbeiro', 'barbeiro_chefe'].includes(f.perfil) && <button disabled={!!formulario || !!vinculos} onClick={() => setJornada(f)}>Jornada</button>}</td></tr>)}
    </tbody></table></div>
  </section>;
}
