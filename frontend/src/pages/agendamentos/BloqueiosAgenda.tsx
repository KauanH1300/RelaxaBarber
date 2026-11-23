import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import axios from 'axios';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { mensagemErro, escritaIncerta } from '../../services/erros';
import { chaveBloqueios, conferirBloqueio, enviarBloqueio, lerEstadoBloqueio, listarBloqueios } from '../../services/bloqueiosAgenda';
import type { Bloqueio, EstadoBloqueio, RascunhoBloqueio } from '../../services/bloqueiosAgenda';

interface Props {
  data: string;
  filialId: string;
  profissionais: { id: string; nome: string }[];
  usuario: { id: string; perfil: string };
  formulario: boolean;
  onFechar: () => void;
}

const vazio: EstadoBloqueio = {
  rascunho: { barbeiro_id: '', hora_inicio: '', hora_fim: '', motivo: '' }, operacao: null,
};

export function BloqueiosAgenda({ data, filialId, profissionais, usuario, formulario, onFechar }: Props) {
  const chave = chaveBloqueios(usuario.id, filialId, data);
  const [inicial] = useState(() => {
    try { return { estado: lerEstadoBloqueio(chave, vazio), erro: '' }; }
    catch { return { estado: vazio, erro: 'Não foi possível recuperar os dados desta aba. Confira a agenda antes de continuar.' }; }
  });
  const [estado, setEstado] = useState(inicial.estado);
  const [erroLocal, setErroLocal] = useState(inicial.erro);
  const [bloqueios, setBloqueios] = useState<Bloqueio[]>([]);
  const [erroLeitura, setErroLeitura] = useState('');
  const [erroAcao, setErroAcao] = useState('');
  const [sucesso, setSucesso] = useState('');
  const [revisao, setRevisao] = useState(0);
  const [ocupado, setOcupado] = useState(false);
  const [conferido, setConferido] = useState(false);
  const enviando = useRef(false);
  const montado = useRef(false);
  const { rascunho, operacao } = estado;
  const podeGerenciar = (id: string) => usuario.perfil === 'admin' || (usuario.perfil !== 'recepcao' && usuario.id === id);
  const elegiveis = profissionais.filter(p => podeGerenciar(p.id));
  const profissional = rascunho.barbeiro_id || (elegiveis.length === 1 ? elegiveis[0].id : '');

  useEffect(() => {
    montado.current = true;
    return () => { montado.current = false; };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    listarBloqueios(filialId, data, controller.signal)
      .then(itens => { if (!controller.signal.aborted) { setBloqueios(itens); setErroLeitura(''); } })
      .catch((falha: unknown) => { if (!controller.signal.aborted) setErroLeitura(mensagemErro(falha, 'Não foi possível consultar os bloqueios.')); });
    return () => controller.abort();
  }, [data, filialId, revisao]);

  function persistir(proximo: EstadoBloqueio) {
    try {
      if (proximo === vazio) sessionStorage.removeItem(chave);
      else sessionStorage.setItem(chave, JSON.stringify(proximo));
      setErroLocal('');
      return true;
    } catch {
      setErroLocal('Não foi possível salvar a recuperação nesta aba. Mantenha a página aberta e tente novamente.');
      return false;
    }
  }

  function atualizarRascunho(campo: keyof RascunhoBloqueio, valor: string) {
    const proximo = { ...estado, rascunho: { ...rascunho, [campo]: valor } };
    setEstado(proximo);
    persistir(proximo);
  }

  function concluir(pedido: EstadoBloqueio, item?: Bloqueio) {
    const alvo = pedido.operacao;
    const criacao = alvo?.tipo === 'criar';
    const proximo = criacao ? vazio : { ...pedido, operacao: null };
    setEstado(proximo);
    persistir(proximo);
    setErroAcao('');
    setConferido(false);
    setSucesso(criacao ? (item?.revogado_em ? 'O bloqueio foi criado e já consta como removido.' : 'Bloqueio criado com sucesso.')
      : 'Bloqueio removido com sucesso.');
    if (alvo?.tipo === 'remover') setBloqueios(atuais => atuais.filter(bloqueio => bloqueio.id !== alvo.id));
    setRevisao(n => n + 1);
    if (criacao) onFechar();
  }

  async function operar(pedido: EstadoBloqueio, consulta = false) {
    const alvo = pedido.operacao;
    if (!alvo || enviando.current) return;
    const marca = contextoAtual();
    const mesmoContexto = () => montado.current && contextoValido(marca);
    if (marca.filialId !== filialId) return;
    if (!consulta && !persistir(pedido)) return;
    enviando.current = true;
    setOcupado(true);
    setEstado(pedido);
    setConferido(false);
    setErroAcao('');
    setSucesso('');
    try {
      if (consulta) {
        const item = await conferirBloqueio(filialId, alvo);
        if (!mesmoContexto()) return;
        if (alvo.tipo === 'criar' || item.revogado_em) concluir(pedido, item);
        else setConferido(true);
      } else {
        const item = await enviarBloqueio(filialId, data, pedido.rascunho, alvo);
        if (mesmoContexto()) concluir(pedido, item);
      }
    } catch (falha: unknown) {
      if (!mesmoContexto()) return;
      if (consulta && alvo.tipo === 'criar' && axios.isAxiosError(falha) && falha.response?.status === 404) {
        setConferido(true);
      } else if (consulta) {
        setErroAcao(mensagemErro(falha, 'Não foi possível conferir a operação.'));
      } else if (escritaIncerta(falha)) {
        setErroAcao('O resultado ainda não foi confirmado. Confira antes de repetir.');
      } else {
        const proximo = { ...pedido, operacao: null };
        setEstado(proximo);
        persistir(proximo);
        setErroAcao(mensagemErro(falha, 'Não foi possível alterar o bloqueio.'));
        setRevisao(n => n + 1);
      }
    } finally {
      enviando.current = false;
      if (montado.current) setOcupado(false);
    }
  }

  function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (operacao || enviando.current) return;
    if (!profissional || !rascunho.motivo.trim() || rascunho.hora_inicio >= rascunho.hora_fim) {
      setErroAcao('Selecione o profissional e informe o motivo e um horário final posterior ao início.');
      return;
    }
    void operar({ rascunho: { ...rascunho, barbeiro_id: profissional }, operacao: { tipo: 'criar', chave: crypto.randomUUID() } });
  }

  const recuperacao = operacao && <div>
    <p role="status">{ocupado ? 'Processando bloqueio…' : conferido
      ? (operacao.tipo === 'criar' ? 'A criação ainda não foi encontrada. Você pode repetir com a mesma chave.'
        : 'O bloqueio continua ativo. Você pode repetir a remoção deste bloqueio.')
      : 'Há uma operação pendente. Confira o resultado antes de repetir.'}</p>
    <button type="button" disabled={ocupado} onClick={() => void operar(estado, true)}>Conferir operação</button>
    {conferido && <button type="button" disabled={ocupado} onClick={() => void operar(estado)}>
      {operacao.tipo === 'criar' ? 'Repetir criação' : 'Repetir remoção'}
    </button>}
  </div>;

  return <section aria-label="Bloqueios de horários">
    {sucesso && <p role="status">{sucesso}</p>}
    {erroLeitura && <p role="alert">{erroLeitura} <button type="button" onClick={() => setRevisao(n => n + 1)}>Atualizar bloqueios</button></p>}
    {!formulario && erroLocal && <p role="alert">{erroLocal}</p>}
    {!formulario && erroAcao && <p role="alert">{erroAcao}</p>}
    {!formulario && recuperacao}
    {!!bloqueios.length && <>
      <h2>Horários bloqueados</h2>
      <ul>{bloqueios.map(b => <li key={b.id}>
        {b.hora_inicio.slice(0, 5)}–{b.hora_fim.slice(0, 5)} · {profissionais.find(p => p.id === b.barbeiro_id)?.nome ?? 'Profissional'} · {b.motivo}
        {podeGerenciar(b.barbeiro_id) && <button type="button" disabled={ocupado || !!operacao} onClick={() => {
          if (window.confirm('Remover este bloqueio e liberar o intervalo?')) void operar({ ...estado, operacao: { tipo: 'remover', id: b.id } });
        }}>Remover bloqueio</button>}
      </li>)}</ul>
    </>}
    {formulario && <div className="modal-overlay">
      <section className="modal-box" role="dialog" aria-modal="true" aria-labelledby="bloqueio-titulo">
        <h2 id="bloqueio-titulo">Bloquear horário</h2>
        <p>{data.split('-').reverse().join('/')} · America/Recife</p>
        {erroLocal && <p role="alert">{erroLocal}</p>}
        {erroAcao && <p role="alert">{erroAcao}</p>}
        <form onSubmit={salvar}>
          <fieldset disabled={ocupado || !!operacao}>
            <label className="modal-campo">Profissional<select name="profissional" value={profissional}
              onChange={e => atualizarRascunho('barbeiro_id', e.target.value)} required>
              <option value="">Selecione…</option>{elegiveis.map(p => <option key={p.id} value={p.id}>{p.nome}</option>)}
            </select></label>
            <label className="modal-campo">Início<input name="inicio" type="time" value={rascunho.hora_inicio}
              onChange={e => atualizarRascunho('hora_inicio', e.target.value)} required /></label>
            <label className="modal-campo">Fim<input name="fim" type="time" value={rascunho.hora_fim}
              onChange={e => atualizarRascunho('hora_fim', e.target.value)} required /></label>
            <label className="modal-campo">Motivo<input name="motivo" maxLength={1000} value={rascunho.motivo}
              onChange={e => atualizarRascunho('motivo', e.target.value)} required /></label>
            <button className="modal-btn-salvar" type="submit">Confirmar bloqueio</button>
          </fieldset>
        </form>
        {recuperacao}
        <button className="modal-btn-cancelar" type="button" disabled={ocupado} onClick={onFechar}>Fechar</button>
      </section>
    </div>}
  </section>;
}
