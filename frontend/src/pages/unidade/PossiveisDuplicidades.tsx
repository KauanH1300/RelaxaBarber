import { useEffect, useId, useRef, useState } from 'react';
import { enviarDecisao, erroCliente, listarDuplicidades, listarRevisoes, localizarContaOnline } from '../../services/clientes';
import type { AcaoDuplicidade, DecisaoDuplicidade, GrupoDuplicidade, MetodoConferencia, RevisaoDuplicidade } from '../../services/clientes';
import { escritaIncerta, mensagemErro } from '../../services/erros';

const acoes: Record<AcaoDuplicidade, string> = {
  encaminhar: 'Encaminhar para ADMIN', associar: 'Associar cadastros',
  diferentes: 'Marcar como pessoas diferentes', reabrir: 'Reabrir análise', desfazer: 'Desfazer associação',
};
const estados = { encaminhado: 'Encaminhado', diferentes: 'Pessoas diferentes', associado: 'Associado', reaberto: 'Reaberto' };

function AcaoPar({ filialId, a, b, revisao, administrador, mudou, parComConta, emailConta }: {
  filialId: string; a: string; b: string; revisao?: RevisaoDuplicidade;
  administrador: boolean; mudou: () => void;
  parComConta?: boolean; emailConta?: string;
}) {
  const [acao, setAcao] = useState<AcaoDuplicidade | ''>(emailConta ? 'associar' : '');
  const [justificativa, setJustificativa] = useState('');
  const [metodo, setMetodo] = useState<MetodoConferencia | ''>('');
  const [confirmado, setConfirmado] = useState(false);
  const [pendente, setPendente] = useState<DecisaoDuplicidade | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState('');
  const enviando = useRef(false);
  const opcoes: AcaoDuplicidade[] = emailConta ? ['associar'] : revisao?.estado === 'associado' ? (administrador ? ['desfazer'] : [])
    : revisao?.estado === 'diferentes' ? (administrador ? ['reabrir'] : [])
    : administrador ? ['associar', 'diferentes']
    : [...(parComConta ? ['associar' as const] : []), ...(revisao?.estado === 'encaminhado' ? [] : ['encaminhar' as const])];
  const verifica = acao === 'associar' || acao === 'diferentes';
  const titularidade = acao === 'associar' && (!!emailConta || !administrador || !!parComConta);
  if (!opcoes.length) return null;
  async function gravar(event: React.FormEvent) {
    event.preventDefault();
    if (!acao || enviando.current || (verifica && (!confirmado || (!titularidade && !metodo)))) return;
    const dados = pendente ?? {
      cliente_a: a, cliente_b: b, versao: revisao?.versao ?? null, chave: crypto.randomUUID(),
      acao, justificativa, identidade_confirmada: verifica && confirmado,
      metodo: titularidade ? 'presencial_e_controle_da_conta' : verifica && metodo ? metodo : null,
      ...(emailConta ? { email_conta: emailConta } : {}),
    };
    enviando.current = true; setOcupado(true); setErro('');
    try {
      await enviarDecisao(filialId, dados);
      mudou();
    } catch (falha) {
      setPendente(escritaIncerta(falha) ? dados : null);
      setErro(mensagemErro(falha, 'Não foi possível confirmar a decisão.'));
    } finally { enviando.current = false; setOcupado(false); }
  }
  return <form onSubmit={event => void gravar(event)}>
    <fieldset disabled={ocupado || !!pendente}>
      {!emailConta && <label>Ação<select value={acao} onChange={e => { setAcao(e.target.value as AcaoDuplicidade | ''); setConfirmado(false); setMetodo(''); }}>
        <option value="">Selecione</option>
        {opcoes.map(item => <option key={item} value={item}>{acoes[item]}</option>)}
      </select></label>}
      {acao && <>
        <label>Justificativa<input required minLength={3} maxLength={500} value={justificativa}
          onChange={e => setJustificativa(e.target.value)} /></label>
        <p className="cliente-nota">Registre apenas o motivo da decisão. Evite CPF, documentos e dados sensíveis.</p>
      </>}
      {verifica && <>
        {!titularidade && <label>Método de conferência<select required value={metodo} onChange={e => setMetodo(e.target.value as MetodoConferencia | '')}>
          <option value="">Selecione o método utilizado</option>
          <option value="presencial_e_atendimentos">Conferência presencial e confirmação de atendimentos</option>
          <option value="identidade_e_controle_da_conta">Verificação de identidade e de controle da conta</option>
          <option value="presencial_e_controle_da_conta">Conferência presencial de titularidade da conta</option>
        </select></label>}
        <label><input type="checkbox" required checked={confirmado} onChange={e => setConfirmado(e.target.checked)} />
          {titularidade ? 'Confirmei presencialmente que a ficha e a conta online pertencem à mesma pessoa e que ela controla a conta.'
            : 'Confirmei a identidade com evidência independente de nome, telefone e e-mail.'}</label>
      </>}
    </fieldset>
    {erro && <p role="alert">{erro}</p>}
    {pendente && <p role="status">O resultado está incerto. Confirme novamente a mesma decisão.</p>}
    {acao && <button type="submit" disabled={ocupado}>{pendente ? 'Confirmar mesma decisão' : acoes[acao]}</button>}
  </form>;
}

const chavePar = (a: string, b: string) => [a, b].sort().join(':');

export function AssociarContaOnline({ filialId, presencialId, administrador, mudou }: {
  filialId: string; presencialId: string; administrador: boolean; mudou: () => void;
}) {
  const [email, setEmail] = useState('');
  const [resultado, setResultado] = useState<{ id: string; nome: string; email: string } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState('');
  const buscando = useRef(false);

  async function buscar(event: React.FormEvent) {
    event.preventDefault();
    if (buscando.current) return;
    buscando.current = true; setOcupado(true); setAviso('');
    const informado = email.trim();
    try {
      const conta = await localizarContaOnline(filialId, presencialId, informado);
      if (conta) setResultado({ ...conta, email: informado });
      else setAviso('Nenhuma conta disponível com esse e-mail e o telefone da ficha.');
    } catch (falha) {
      setAviso(erroCliente(falha, 'Não foi possível consultar a conta online'));
    } finally { buscando.current = false; setOcupado(false); }
  }

  return <details><summary>Associar conta online à ficha presencial</summary>
    {resultado ? <>
      <p>Conta localizada: {resultado.nome}</p>
      <AcaoPar filialId={filialId} a={presencialId} b={resultado.id} administrador={administrador}
        emailConta={resultado.email} mudou={mudou} />
    </> : <form onSubmit={event => void buscar(event)}>
      <label>E-mail confirmado na conta online<input type="email" required maxLength={255} value={email}
        onChange={event => setEmail(event.target.value)} disabled={ocupado} /></label>
      <button type="submit" disabled={ocupado}>{ocupado ? 'Buscando…' : 'Localizar conta'}</button>
    </form>}
    {aviso && <p role="status">{aviso}</p>}
  </details>;
}

export function PossiveisDuplicidades({ filialId, selecionar, administrador, mudou }: {
  filialId: string; selecionar: (id: string) => void; administrador: boolean; mudou: () => void;
}) {
  const [grupos, setGrupos] = useState<GrupoDuplicidade[] | null>(null);
  const [revisoes, setRevisoes] = useState<RevisaoDuplicidade[]>([]);
  const [erro, setErro] = useState('');
  const [tentativa, setTentativa] = useState(0);
  const titulo = useId();
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([listarDuplicidades(filialId, controller.signal), listarRevisoes(filialId, controller.signal)]).then(([resultado, analises]) => {
      if (!controller.signal.aborted) { setGrupos(resultado); setRevisoes(analises); }
    }).catch(falha => {
      if (!controller.signal.aborted) setErro(erroCliente(falha, 'Não foi possível consultar possíveis duplicidades'));
    });
    return () => controller.abort();
  }, [filialId, tentativa]);
  const porPar = new Map(revisoes.map(r => [chavePar(r.cliente_a, r.cliente_b), r]));
  const mostrados = new Set<string>();
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
          {grupo.clientes.flatMap((a, indice) => grupo.clientes.slice(indice + 1).map(b => {
            const chave = chavePar(a.id, b.id);
            const revisao = porPar.get(chave);
            if (revisao?.estado === 'associado' || revisao?.estado === 'diferentes') return null;
            mostrados.add(chave);
            return <details key={chave}><summary>{a.nome} e {b.nome}{revisao && ` · ${estados[revisao.estado]}`}</summary>
              <AcaoPar filialId={filialId} a={a.id} b={b.id} revisao={revisao}
                administrador={administrador} parComConta={a.conta_ativada !== b.conta_ativada} mudou={mudou} />
            </details>;
          }))}
        </details>)}
      </>}
    {!!revisoes.length && <details><summary>Revisões registradas</summary>
      {revisoes.filter(r => !mostrados.has(chavePar(r.cliente_a, r.cliente_b))).map(r =>
        <details key={chavePar(r.cliente_a, r.cliente_b)}>
          <summary>{r.nome_a} e {r.nome_b} · {estados[r.estado]}</summary>
          {r.principal_id && <button type="button" onClick={() => selecionar(r.principal_id!)}>Ver ficha principal</button>}
          <AcaoPar filialId={filialId} a={r.cliente_a} b={r.cliente_b} revisao={r} administrador={administrador} mudou={mudou} />
        </details>)}
    </details>}
  </section>;
}
