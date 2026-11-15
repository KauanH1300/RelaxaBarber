import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type { Comanda } from '../../services/comandas';
import { moeda } from '../../services/comandas';
import { erroFinanceiro, resultadoIncerto } from '../../services/financeiro';
import { useUsuario } from '../../services/usuario';
import { catalogoItens, chaveInclusao, incluirServico, lerInclusao, limparInclusao, permiteInclusao, salvarInclusao } from '../../services/itensComanda';
import type { InclusaoPendente, ServicoParaComanda } from '../../services/itensComanda';

export function AdicionarServico({ comanda, bloqueado, aoBloqueio, aoAtualizar }: { comanda: Comanda; bloqueado: boolean; aoBloqueio: (b: boolean) => void; aoAtualizar: () => void }) {
  const usuario = useUsuario();
  const storage = chaveInclusao(usuario.id, comanda);
  const [recuperacao] = useState(() => {
    try { return { pendente: lerInclusao(storage), erro: '' }; }
    catch { return { pendente: null, erro: 'Não foi possível recuperar a inclusão. Preserve o registro temporário e procure o administrador.' }; }
  });
  const [pendente, setPendente] = useState(recuperacao.pendente);
  const [aberto, setAberto] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [servicos, setServicos] = useState<ServicoParaComanda[]>([]);
  const [servicoId, setServicoId] = useState('');
  const [quantidade, setQuantidade] = useState('1');
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');
  const [tentativa, setTentativa] = useState(0);
  const trava = useRef(false);
  const montado = useRef(true);
  const seletor = useRef<HTMLSelectElement>(null);
  const botao = useRef<HTMLButtonElement>(null);
  useEffect(() => { montado.current = true; return () => { montado.current = false; }; }, []);
  useEffect(() => { aoBloqueio(aberto || ocupado || !!pendente || !!recuperacao.erro); }, [aberto, ocupado, pendente, recuperacao.erro, aoBloqueio]);
  useEffect(() => {
    if (!aberto) return;
    const controller = new AbortController();
    catalogoItens(controller.signal).then((data) => { if (!controller.signal.aborted) setServicos(data); })
      .catch(() => { if (!controller.signal.aborted) setErro('Não foi possível carregar os serviços. Tente novamente.'); })
      .finally(() => { if (!controller.signal.aborted) { setCarregando(false); seletor.current?.focus(); } });
    return () => controller.abort();
  }, [aberto, tentativa]);
  const permitido = permiteInclusao(usuario, comanda);
  const selecionado = servicos.find((s) => s.id === servicoId);
  const numero = Number(quantidade);
  async function enviar(p: InclusaoPendente, recuperar = false) {
    if (trava.current || bloqueado) return;
    trava.current = true; setOcupado(true); setErro(''); setAviso('');
    let confirmado = false;
    try {
      salvarInclusao(storage, p); setPendente(p);
      await incluirServico(comanda, p); confirmado = true;
      if (montado.current) {
        limparInclusao(storage, p); setPendente(null); setAberto(false);
        setAviso('Serviço adicionado. Atualizando itens, total e indicadores.'); botao.current?.focus();
      }
    } catch (falha) {
      if (montado.current) {
        const status = (falha as { response?: { status?: number } })?.response?.status;
        setErro(!status ? 'Não foi possível confirmar a inclusão. Se houve envio, recupere a mesma operação. Não inicie outra inclusão.' : status === 422 ? 'Verifique o serviço ativo e a quantidade inteira entre 1 e 999.' : erroFinanceiro(falha));
        if (!confirmado && !recuperar && status && !resultadoIncerto(falha)) {
          try { limparInclusao(storage, p); setPendente(null); } catch { /* preservar para recuperação */ }
        }
      }
    } finally {
      trava.current = false;
      if (montado.current) setOcupado(false);
      if (confirmado) aoAtualizar();
    }
  }
  function confirmar(event: FormEvent) {
    event.preventDefault();
    if (!permitido || !selecionado || ocupado || pendente || bloqueado || !Number.isInteger(numero) || numero < 1 || numero > 999) return;
    void enviar({ chave: crypto.randomUUID(), payload: { servico_id: selecionado.id, quantidade: numero } });
  }
  return <section className="comanda-adicionar-servico" aria-label="Adicionar serviço cadastrado" aria-busy={ocupado || carregando}>
    {permitido && !aberto && !pendente && <button ref={botao} type="button" className="comandas-botao-dourado" disabled={bloqueado || !!recuperacao.erro} onClick={() => { setErro(''); setAviso(''); setCarregando(true); setAberto(true); }}>Adicionar serviço</button>}
    {permitido && bloqueado && !pendente && <p>Resolva a consulta ou confirmação financeira antes de adicionar serviços.</p>}
    {recuperacao.erro && <p role="alert">{recuperacao.erro}</p>}
    {erro && <p role="alert">{erro}</p>}{aviso && <p role="status">{aviso}</p>}
    {pendente && <aside role="status"><p>Inclusão aguardando confirmação. Recupere com a mesma chave e os mesmos dados; não adicione novamente.</p><button type="button" disabled={ocupado || bloqueado} onClick={() => void enviar(pendente, true)}>Recuperar inclusão</button></aside>}
    {aberto && !pendente && <form onSubmit={confirmar}>
      {!permitido && <p role="status">O estado atual da comanda não permite novas inclusões.</p>}
      <fieldset disabled={!permitido || ocupado || bloqueado || carregando || !!recuperacao.erro}><legend>Adicionar serviço cadastrado</legend>
        <label>Serviço<select required ref={seletor} value={servicoId} onChange={(e) => setServicoId(e.target.value)}><option value="">Selecione um serviço</option>{servicos.map((s) => <option key={s.id} value={s.id}>{s.nome} · {moeda(String(s.preco))}</option>)}</select></label>
        <label>Quantidade<input required type="number" min="1" max="999" step="1" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} /></label>
        {selecionado && <p>Valor unitário: {moeda(String(selecionado.preco))} · Subtotal previsto: {Number.isInteger(numero) && numero >= 1 && numero <= 999 ? moeda(String(Math.round(selecionado.preco * 100) * numero / 100)) : '—'}</p>}
        <p>O preço definitivo será validado no servidor na confirmação. O horário do atendimento não será alterado.</p>
        <button type="submit" className="comandas-botao-dourado" disabled={!selecionado}>Confirmar inclusão</button>
      </fieldset>
      <button type="button" disabled={ocupado} onClick={() => { setAberto(false); botao.current?.focus(); }}>Cancelar inclusão</button>
      <button type="button" disabled={carregando || ocupado} onClick={() => { setErro(''); setCarregando(true); setTentativa((n) => n + 1); }}>Atualizar catálogo</button>
    </form>}
  </section>;
}
