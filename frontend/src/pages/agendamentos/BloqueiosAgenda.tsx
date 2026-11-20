import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import api from '../../services/api';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { mensagemErro, escritaIncerta } from '../../services/erros';

interface Bloqueio {
  id: string;
  barbeiro_id: string;
  hora_inicio: string;
  hora_fim: string;
  motivo: string;
}

interface Props {
  data: string;
  profissionais: { id: string; nome: string }[];
  usuario: { id: string; perfil: string };
  formulario: boolean;
  onFechar: () => void;
}

export function BloqueiosAgenda({ data, profissionais, usuario, formulario, onFechar }: Props) {
  const [bloqueios, setBloqueios] = useState<Bloqueio[] | null>(null);
  const [erroLeitura, setErroLeitura] = useState('');
  const [erroAcao, setErroAcao] = useState('');
  const [revisao, setRevisao] = useState(0);
  const [salvando, setSalvando] = useState(false);
  const [incerto, setIncerto] = useState(false);
  const enviando = useRef(false);
  const podeGerenciar = (id: string) => usuario.perfil === 'admin' || (usuario.perfil !== 'recepcao' && usuario.id === id);
  const elegiveis = profissionais.filter(p => podeGerenciar(p.id));

  useEffect(() => {
    const controller = new AbortController();
    api.get<Bloqueio[]>('/agendamentos/bloqueios', { params: { data }, signal: controller.signal })
      .then(({ data: itens }) => { if (!controller.signal.aborted) { setBloqueios(itens); setErroLeitura(''); } })
      .catch((e: unknown) => { if (!controller.signal.aborted) setErroLeitura(mensagemErro(e, 'Não foi possível consultar os bloqueios.')); });
    return () => controller.abort();
  }, [data, revisao]);

  async function alterar(operacao: () => Promise<unknown>, aoSalvar?: () => void) {
    if (enviando.current) return;
    const marca = contextoAtual();
    enviando.current = true;
    setSalvando(true);
    setErroAcao('');
    try {
      await operacao();
      if (contextoValido(marca)) {
        setRevisao(n => n + 1);
        aoSalvar?.();
      }
    } catch (e: unknown) {
      if (!contextoValido(marca)) return;
      const deveConferir = escritaIncerta(e);
      setErroAcao(mensagemErro(e, 'Não foi possível alterar o bloqueio.') +
        (deveConferir ? ' Confira a agenda antes de repetir.' : ''));
      if (deveConferir) { setIncerto(true); setRevisao(n => n + 1); }
    } finally {
      enviando.current = false;
      setSalvando(false);
    }
  }

  function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const dados = new FormData(event.currentTarget);
    const motivo = String(dados.get('motivo') ?? '').trim();
    const inicio = String(dados.get('inicio') ?? '');
    const fim = String(dados.get('fim') ?? '');
    if (!motivo || inicio >= fim) {
      setErroAcao('Informe o motivo e um horário final posterior ao início.');
      return;
    }
    void alterar(() => api.post('/agendamentos/bloqueios', {
      data, barbeiro_id: dados.get('profissional'), hora_inicio: inicio, hora_fim: fim, motivo,
      filial_id: contextoAtual().filialId,
    }), onFechar);
  }

  return <section aria-label="Bloqueios de horários">
    {erroLeitura && <p role="alert">{erroLeitura} <button type="button" onClick={() => setRevisao(n => n + 1)}>Atualizar bloqueios</button></p>}
    {erroAcao && !formulario && <p role="alert">{erroAcao}</p>}
    {!!bloqueios?.length && <>
      <h2>Horários bloqueados</h2>
      <ul>{bloqueios.map(b => <li key={b.id}>
        {b.hora_inicio.slice(0, 5)}–{b.hora_fim.slice(0, 5)} · {profissionais.find(p => p.id === b.barbeiro_id)?.nome ?? 'Profissional'} · {b.motivo}
        {podeGerenciar(b.barbeiro_id) && <button type="button" disabled={salvando} onClick={() => {
          if (window.confirm('Remover este bloqueio e liberar o intervalo?')) void alterar(() => api.delete('/agendamentos/bloqueios/' + b.id));
        }}>Remover bloqueio</button>}
      </li>)}</ul>
    </>}
    {formulario && <div className="modal-overlay">
      <section className="modal-box" role="dialog" aria-modal="true" aria-labelledby="bloqueio-titulo">
        <h2 id="bloqueio-titulo">Bloquear horário</h2>
        <p>{data.split('-').reverse().join('/')} · America/Recife</p>
        {erroAcao && <p role="alert">{erroAcao}</p>}
        <form onSubmit={salvar}>
          <fieldset disabled={salvando || incerto}>
            <label className="modal-campo">Profissional<select name="profissional" defaultValue={elegiveis.length === 1 ? elegiveis[0].id : ''} required>
              <option value="">Selecione…</option>{elegiveis.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></label>
            <label className="modal-campo">Início<input name="inicio" type="time" required /></label>
            <label className="modal-campo">Fim<input name="fim" type="time" required /></label>
            <label className="modal-campo">Motivo<input name="motivo" maxLength={1000} required /></label>
            <button className="modal-btn-salvar" type="submit">{salvando ? 'Salvando…' : 'Confirmar bloqueio'}</button>
          </fieldset>
        </form>
        <button className="modal-btn-cancelar" type="button" disabled={salvando} onClick={() => {
          setIncerto(false); setErroAcao(''); onFechar();
        }}>Fechar</button>
      </section>
    </div>}
  </section>;
}
