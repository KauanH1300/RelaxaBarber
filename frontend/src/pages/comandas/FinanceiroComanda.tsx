import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { Comanda } from '../../services/comandas';
import { instanteRecife, moeda } from '../../services/comandas';
import { useUsuario } from '../../services/usuario';
import { agoraLocal, centavos, chaveStorage, consultarFinanceiro, dataEfetiva, decimal, enviarFinanceiro, erroFinanceiro, formasPagamento, lerPendente, limparPendente, pagamentosComEstornos, podeConsultar, podeMovimentar, prepararFechamento, recuperarFinanceiro, resultadoIncerto, salvarPendente } from '../../services/financeiro';
import type { FormaPagamento, Intencao, ParcelaFormulario, Pendente, ResumoFinanceiro } from '../../services/financeiro';
import { HistoricoComanda } from './HistoricoComanda';

type Parcela = ParcelaFormulario & { id: string };
const novaParcela = (): Parcela => ({ id: crypto.randomUUID(), valor: '', forma: 'pix', confirmado: false });
const titulos = { pagamentos: 'Recuperar pagamento antigo', estornos: 'Registrar estorno', 'fechamento-financeiro': 'Receber e fechar comanda' };

interface Coordenacao { bloqueioExterno?: boolean; aoBloqueio?: (b: boolean) => void }
export function FinanceiroComanda({ comanda, aoConfirmar, bloqueioExterno, aoBloqueio }: { comanda: Comanda; aoConfirmar?: () => void } & Coordenacao) {
  const usuario = useUsuario();
  if (!podeConsultar(usuario, comanda)) return <section className="comanda-financeiro"><h3>Financeiro</h3><p>Consulta financeira restrita às suas próprias comandas.</p></section>;
  return <PainelFinanceiro key={`${usuario.id}:${comanda.filial_id}:${comanda.id}`} comanda={comanda} usuarioId={usuario.id} admin={usuario.perfil === 'admin'} aoConfirmar={aoConfirmar} bloqueioExterno={bloqueioExterno} aoBloqueio={aoBloqueio} />;
}

function PainelFinanceiro({ comanda, usuarioId, admin, aoConfirmar, bloqueioExterno, aoBloqueio }: { comanda: Comanda; usuarioId: string; admin: boolean; aoConfirmar?: () => void } & Coordenacao) {
  const storage = chaveStorage(usuarioId, comanda);
  const [resumo, setResumo] = useState<ResumoFinanceiro | null>(null);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [revisao, setRevisao] = useState(0);
  const [recuperacao] = useState(() => {
    try { return { pendente: lerPendente(storage), erro: '' }; }
    catch { return { pendente: null, erro: 'Não foi possível recuperar o registro temporário. Preserve os dados e procure o administrador antes de lançar novamente.' }; }
  });
  const [pendente, setPendente] = useState<Pendente | null>(recuperacao.pendente);
  const [confirmacao, setConfirmacao] = useState<Intencao | null>(null);
  const [parcelas, setParcelas] = useState<Parcela[]>(() => [novaParcela()]);
  const [data, setData] = useState(agoraLocal);
  const [motivo, setMotivo] = useState('');
  const [valorEstorno, setValorEstorno] = useState('');
  const [motivoEstorno, setMotivoEstorno] = useState('');
  const [dataEstorno, setDataEstorno] = useState(agoraLocal);
  const [pagamentoId, setPagamentoId] = useState('');
  const trava = useRef(false);
  const montado = useRef(true);
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController();
    consultarFinanceiro(comanda, controller.signal).then((dados) => {
      if (!controller.signal.aborted) setResumo(dados);
    }).catch((falha: unknown) => {
      if (!controller.signal.aborted) {
        setResumo(null);
        const status = (falha as { response?: { status?: number } })?.response?.status;
        setErro(status && status < 500 ? erroFinanceiro(falha) : 'Não foi possível consultar o financeiro. Use Consultar estado para atualizar os dados, sem refazer uma cobrança já confirmada.');
      }
    }).finally(() => { if (!controller.signal.aborted) setCarregando(false); });
    return () => controller.abort();
  }, [comanda, revisao]);
  function atualizar() { setCarregando(true); setConfirmacao(null); setRevisao((n) => n + 1); }
  const movimentavel = resumo && podeMovimentar(comanda, resumo);
  const bloqueado = ocupado || carregando || !!pendente || !!recuperacao.erro || !!confirmacao || !!bloqueioExterno;
  useEffect(() => { aoBloqueio?.(ocupado || carregando || !!pendente || !!recuperacao.erro || !!confirmacao); }, [ocupado, carregando, pendente, recuperacao.erro, confirmacao, aoBloqueio]);
  const pagamentos = resumo && resumo.situacao !== 'nao_verificado' ? pagamentosComEstornos(resumo.historico) : [];
  function alterarParcela(id: string, mudanca: Partial<ParcelaFormulario>) {
    setParcelas((atuais) => atuais.map((p) => p.id === id ? { ...p, ...mudanca, confirmado: mudanca.confirmado ?? false } : p));
  }
  function preparar(event: FormEvent) {
    event.preventDefault();
    if (!resumo || !movimentavel || bloqueado) return;
    setErro(''); setAviso('');
    try {
      const payload = prepararFechamento(resumo, resumo.saldo === '0.00' ? [] : parcelas, data, motivo, admin);
      setConfirmacao({ operacao: 'fechamento-financeiro', payload });
    } catch (falha) { setErro((falha as Error).message); }
  }
  function prepararEstorno(event: FormEvent) {
    event.preventDefault();
    if (!admin || !movimentavel || bloqueado) return;
    setErro(''); setAviso('');
    try {
      const pagamento = pagamentos.find((p) => p.id === pagamentoId);
      const quantia = centavos(valorEstorno);
      if (!pagamento || quantia <= 0 || quantia > centavos(pagamento.liquido)) throw new Error('Selecione um pagamento e um valor dentro do limite disponível.');
      if (!motivoEstorno.trim()) throw new Error('Informe o motivo do estorno.');
      setConfirmacao({ operacao: 'estornos', payload: { pagamento_id: pagamento.id, valor: decimal(quantia), motivo: motivoEstorno.trim(), efetivado_em: dataEfetiva(dataEstorno, true, pagamento.recebido_em) } });
    } catch (falha) { setErro((falha as Error).message); }
  }
  async function enviar(operacao: Pendente, recuperar = false) {
    if (trava.current) return;
    trava.current = true; setOcupado(true); setErro(''); setAviso('');
    try {
      // Não substituir uma intenção anterior nem emitir POST sem persistência.
      if (!recuperar) salvarPendente(storage, operacao);
      setPendente(operacao); setConfirmacao(null);
    } catch {
      setErro('Não foi possível preservar a operação. Nenhuma requisição foi enviada. Confira o armazenamento e a pendência anterior.');
      trava.current = false; setOcupado(false); return;
    }
    let confirmada = false;
    try {
      if (recuperar) await recuperarFinanceiro(comanda, storage);
      else if (operacao.operacao !== 'pagamentos') await enviarFinanceiro(comanda, operacao);
      else throw new Error('Pagamento antigo deve ser recuperado do registro original.');
      confirmada = true;
      // Uma nova montagem pode já ter carregado esta intenção. A instância
      // desmontada não a apaga por trás do diálogo reaberto durante o POST.
      if (montado.current) {
        try { limparPendente(storage, operacao); setPendente(null); }
        catch { setErro('Operação confirmada, mas o registro temporário não pôde ser removido. Preserve a chave original para recuperação.'); }
        setAviso('Operação confirmada. Atualizando comanda, resumo e indicadores.');
        setParcelas([novaParcela()]); setMotivo(''); setPagamentoId(''); setValorEstorno(''); setMotivoEstorno(''); setData(agoraLocal());
      }
    } catch (falha) {
      if (montado.current) setErro(erroFinanceiro(falha));
      if (montado.current && !recuperar && !resultadoIncerto(falha)) {
        try { limparPendente(storage, operacao); if (montado.current) setPendente(null); }
        catch { if (montado.current) setErro('Preserve o registro temporário e procure o administrador.'); }
      }
    } finally {
      if (montado.current) { setResumo(null); atualizar(); setOcupado(false); }
      trava.current = false;
    }
    if (confirmada) aoConfirmar?.();
  }
  let soma: number | null = null;
  try { soma = parcelas.reduce((total, p) => total + (p.valor ? centavos(p.valor) : 0), 0); } catch { /* entrada incompleta */ }
  const quitada = resumo?.saldo === '0.00';
  return <section className="comanda-financeiro" aria-labelledby="financeiro-titulo" aria-busy={ocupado || carregando}>
    <header><h3 id="financeiro-titulo">Financeiro da comanda</h3><button type="button" disabled={ocupado || carregando} onClick={() => { setErro(''); atualizar(); }}>Consultar estado</button></header>
    <p>Concluir o atendimento não fecha a comanda. O fechamento exige quitação integral confirmada.</p>
    {carregando && <p role="status">Consultando financeiro…</p>}
    {erro && <p role="alert" className="financeiro-erro">{erro}</p>}
    {recuperacao.erro && <p role="alert">{recuperacao.erro}</p>}
    {aviso && <p role="status">{aviso}</p>}
    {resumo && !carregando && <>
      <strong className={`financeiro-situacao financeiro-situacao-${resumo.situacao}`}>Situação financeira: {resumo.situacao === 'nao_verificado' ? 'Não verificado' : resumo.situacao === 'fechado' ? 'Fechado' : quitada ? 'Quitado · aguardando fechamento' : 'Aberto'}</strong>
      <dl className="financeiro-resumo">{([['Valor Total', resumo.total], ['Valor Recebido', resumo.recebido_liquido]] as const).map(([rotulo, quantia]) => <div key={rotulo}><dt>{rotulo}</dt><dd>{quantia === null ? 'Não verificado' : moeda(quantia)}</dd></div>)}</dl>
      {resumo.situacao === 'nao_verificado' && <p>Comanda legada: não é possível afirmar dívida ou quitação. Recebimento e fechamento bloqueados até conciliação específica.</p>}
      {resumo.situacao === 'fechado' && <p>Financeiro fechado. Novos pagamentos e estornos estão bloqueados.</p>}
      {resumo.situacao === 'aberto' && !movimentavel && <p>Movimentação indisponível no estado atual: exige atendimento concluído e comanda não cancelada.</p>}
    </>}
    {pendente && <aside className="financeiro-pendente" role="status"><strong>Operação aguardando confirmação</strong><p>{titulos[pendente.operacao]}. Não inicie outra cobrança. Consulte o estado e recupere a operação com a chave e os dados originais. Mantenha esta aba aberta até resolver a confirmação.</p>
      {pendente.operacao === 'pagamentos' && <p>Registro antigo: a recuperação consulta o lançamento original. Se ele não existia, o backend rejeita a criação avulsa. Preserve a pendência para revisão com o administrador.</p>}
      <small>Chave: {pendente.chave}</small><button type="button" disabled={ocupado || carregando || !resumo} onClick={() => void enviar(pendente, true)}>Recuperar operação original</button></aside>}
    {movimentavel && !pendente && !recuperacao.erro && <>
      <form onSubmit={preparar} className="financeiro-form" data-operacao="fechamento-financeiro">
        <fieldset disabled={bloqueado}><legend>{quitada ? 'Finalizar comanda quitada' : 'Recebimento integral e fechamento'}</legend>
          {quitada ? <p>Valor integral já registrado. Finalize sem cobrar novamente.</p> : <>
            <p>Valor restante a confirmar: <strong>{moeda(resumo.saldo!)}</strong>. A soma deve quitar todo esse valor na mesma operação.</p>
            {parcelas.map((p, indice) => <div className="financeiro-parcela" key={p.id}>
              <h4>Recebimento {indice + 1}</h4>
              <div className="financeiro-parcela-campos"><label>Forma de pagamento {indice + 1}<select value={p.forma} onChange={(e) => alterarParcela(p.id, { forma: e.target.value as FormaPagamento })}>{Object.entries(formasPagamento).map(([valor, nome]) => <option key={valor} value={valor}>{nome}</option>)}</select></label>
              <label>Valor recebido {indice + 1} (R$)<input required inputMode="decimal" value={p.valor} onChange={(e) => alterarParcela(p.id, { valor: e.target.value })} placeholder="0,00" /></label></div>
              <label className="financeiro-check"><input type="checkbox" checked={p.confirmado} onChange={(e) => alterarParcela(p.id, { confirmado: e.target.checked })} />Confirmo o recebimento {indice + 1} por {formasPagamento[p.forma]}</label>
              <button type="button" disabled={parcelas.length === 1} onClick={() => setParcelas((atuais) => atuais.filter((r) => r.id !== p.id))}>Remover recebimento {indice + 1}</button>
            </div>)}
            <button type="button" disabled={parcelas.length >= 16} onClick={() => setParcelas((atuais) => atuais.length < 16 ? [...atuais, novaParcela()] : atuais)}>Adicionar forma de pagamento</button>
            <p>Soma informada: {soma === null ? 'Valor inválido' : moeda(decimal(soma))}. Não é permitido deixar saldo para pagamento futuro.</p>
            <label>Data/hora dos recebimentos · fuso deste dispositivo<input required type="datetime-local" value={data} onChange={(e) => { setData(e.target.value); setParcelas((atuais) => atuais.map((p) => ({ ...p, confirmado: false }))); }} /></label>
          </>}
          <label>Motivo{resumo.total !== '0.00' ? ' (opcional)' : ''}<textarea required={resumo.total === '0.00'} value={motivo} onChange={(e) => setMotivo(e.target.value)} /></label>
          <button type="submit" className="comandas-botao-dourado">{quitada ? 'Revisar fechamento sem cobrança' : 'Revisar recebimento integral'}</button>
        </fieldset>
      </form>
      {admin && <details className="financeiro-estorno"><summary>Estornar pagamento histórico</summary><p>Somente pagamentos de comandas financeiramente abertas podem receber novos estornos.</p>
        <form onSubmit={prepararEstorno} className="financeiro-form" data-operacao="estornos"><fieldset disabled={bloqueado}><legend>Estorno administrativo</legend>
          <label>Pagamento elegível para estorno<select required value={pagamentoId} onChange={(e) => setPagamentoId(e.target.value)}><option value="">Selecione</option>{pagamentos.filter((p) => centavos(p.liquido) > 0).map((p) => <option key={p.id} value={p.id}>{formasPagamento[p.forma]} · {instanteRecife(p.recebido_em)} · Disponível: {moeda(p.liquido)} · {p.id.slice(-8)}</option>)}</select></label>
          <label>Valor do estorno (R$)<input required inputMode="decimal" value={valorEstorno} onChange={(e) => setValorEstorno(e.target.value)} /></label>
          <label>Data/hora do estorno · fuso deste dispositivo<input required type="datetime-local" value={dataEstorno} onChange={(e) => setDataEstorno(e.target.value)} /></label>
          <label>Motivo do estorno<textarea required value={motivoEstorno} onChange={(e) => setMotivoEstorno(e.target.value)} /></label>
          <button type="submit">Revisar estorno</button>
        </fieldset></form>
      </details>}
    </>}
    {confirmacao && <div className="financeiro-confirmacao" role="group" aria-label="Confirmação financeira"><h4>Confirmar: {titulos[confirmacao.operacao]}</h4>
      {confirmacao.operacao === 'fechamento-financeiro' ? <><p>Os recebimentos abaixo e o fechamento serão confirmados juntos.</p>
        {confirmacao.payload.pagamentos?.length ? <ul>{confirmacao.payload.pagamentos.map((p, i) => <li key={i}>{formasPagamento[p.forma]} · {moeda(p.valor)} · {instanteRecife(p.recebido_em)}</li>)}</ul> : <p>Sem nova cobrança: quitação já registrada.</p>}
        <p>Após fechar, novos pagamentos e estornos estarão bloqueados.</p>
      </> : <p>Estornar {moeda(confirmacao.payload.valor)} do pagamento {confirmacao.payload.pagamento_id} · {instanteRecife(confirmacao.payload.efetivado_em)}</p>}
      <p>Motivo: {confirmacao.payload.motivo || 'Sem motivo adicional'}</p>
        <button type="button" className="comandas-botao-dourado" disabled={ocupado || carregando || bloqueioExterno} onClick={() => void enviar({ ...confirmacao, chave: crypto.randomUUID() })}>Confirmar operação</button>
      <button type="button" disabled={ocupado} onClick={() => setConfirmacao(null)}>Voltar</button>
    </div>}
    {resumo && !carregando && <details className="financeiro-historico-area"><summary>Histórico financeiro e estornos</summary><HistoricoComanda resumo={resumo} /><p>Valor Recebido considera pagamentos menos estornos.</p></details>}
  </section>;
}
