import { useEffect, useRef, useState } from 'react';
import { useFilial } from '../../services/filialEstado';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { consultarRestricoesServicos, salvarRestricoesServicos } from '../../services/funcionarios';
import type { RestricoesServicos as Config } from '../../services/funcionarios';
import { escritaIncerta, mensagemErro } from '../../services/erros';

export function RestricoesServicos({ barbeiroId }: { barbeiroId: string }) {
  const { filialId } = useFilial();
  return filialId ? <EditorRestricoes key={`${filialId}:${barbeiroId}`} filialId={filialId} barbeiroId={barbeiroId} /> : <p>Selecione uma filial para editar os serviços que não realiza.</p>;
}

export function EditorRestricoes({ filialId, barbeiroId }: { filialId: string; barbeiroId: string }) {
  const [config, setConfig] = useState<Config | null>(null);
  const [ocupado, setOcupado] = useState(false); const [incerto, setIncerto] = useState(false);
  const [erro, setErro] = useState(''); const [mensagem, setMensagem] = useState('');
  const [versao, setVersao] = useState(0); const trava = useRef(false);
  useEffect(() => {
    const controller = new AbortController(); const contexto = contextoAtual();
    consultarRestricoesServicos(filialId, barbeiroId, controller.signal).then(dados => {
      if (!controller.signal.aborted && contextoValido(contexto)) { setConfig(dados); setErro(''); setIncerto(false); }
    }).catch(falha => { if (!controller.signal.aborted && contextoValido(contexto)) setErro(mensagemErro(falha, 'Não foi possível consultar. Verifique o vínculo ativo do profissional nesta filial.')); });
    return () => controller.abort();
  }, [filialId, barbeiroId, versao]);
  async function salvar(e: React.FormEvent) {
    e.preventDefault(); if (trava.current || !config || incerto) return;
    const contexto = contextoAtual();
    if (contexto.filialId !== filialId || !contexto.token) return;
    trava.current = true; setOcupado(true); setErro(''); setMensagem('');
    try {
      await salvarRestricoesServicos(filialId, barbeiroId, config.restricoes);
      if (contextoValido(contexto)) setMensagem('Serviços que não realiza salvos nesta filial.');
    } catch (falha) {
      if (contextoValido(contexto)) { setErro(mensagemErro(falha, 'Não foi possível salvar os serviços que não realiza.')); setIncerto(escritaIncerta(falha)); }
    } finally { trava.current = false; setOcupado(false); }
  }
  return <section aria-labelledby="restricoes-titulo"><h3 id="restricoes-titulo">Serviços que não realiza</h3>
    <p>Marque somente os serviços que este profissional não realiza na filial selecionada. Nenhuma seleção significa que realiza todos, incluindo novos serviços. As exceções valem para novas reservas; as existentes são preservadas.</p>
    <p>Este salvamento é independente dos demais dados do funcionário.</p>
    {erro && <p role="alert">{erro}</p>}{mensagem && <p role="status">{mensagem}</p>}
    {incerto && <p role="alert">Resultado não confirmado. Consulte novamente antes de salvar.</p>}
    <button type="button" disabled={ocupado} onClick={() => { setConfig(null); setMensagem(''); setVersao(n => n + 1); }}>Consultar serviços novamente</button>
    {!config ? <p role="status">Aguardando consulta dos serviços.</p> : <form onSubmit={e => void salvar(e)}><fieldset disabled={ocupado || incerto}><legend>Exceções na filial selecionada</legend>
      {config.servicos.map(s => <label key={s.id}><input type="checkbox" checked={config.restricoes.includes(s.id)} onChange={e => setConfig({ ...config, restricoes: e.target.checked ? [...config.restricoes, s.id] : config.restricoes.filter(id => id !== s.id) })} />{s.nome}{!s.ativo && ' (inativo)'}</label>)}
      {!config.servicos.length && <p>Nenhum serviço cadastrado.</p>}
      <button type="submit">{ocupado ? 'Salvando…' : 'Salvar serviços que não realiza'}</button>
    </fieldset></form>}
  </section>;
}
