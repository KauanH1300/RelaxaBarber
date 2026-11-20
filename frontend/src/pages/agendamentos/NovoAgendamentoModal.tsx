import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import api from '../../services/api';
import { contextoAtual, contextoValido } from '../../services/filialAtiva';
import { mensagemErro, deveConferirRegistros, escritaAgendaIncerta } from '../../services/erros';

interface Cliente {
  id: string;
  nome: string;
  telefone: string;
}
interface Barbeiro {
  id: string;
  nome: string;
}
interface Servico {
  id: string;
  nome: string;
  preco: number;
  tempo_estimado: number;
}
interface Props {
  aberto: boolean;
  imediato?: boolean;
  dataInicial: string;
  onFechar: () => void;
  onSalvo: (data: string, recuperado: boolean) => void;
  onConferir?: (data: string) => void;
  barbeiros: Barbeiro[];
}

export function NovoAgendamentoModal({ aberto, onFechar, onSalvo,barbeiros, dataInicial, onConferir, imediato = false }: Props) {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [clienteId, setClienteId] = useState('');
  const [barbeiroId, setBarbeiroId] = useState('');
  const [data, setData] = useState(dataInicial);
  const [horaInicio, setHoraInicio] = useState('');
  const [duracao, setDuracao] = useState('');
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [servicosIds, setServicosIds] = useState<string[]>([]);
  const [erro, setErro] = useState('');
  const [erroCarga, setErroCarga] = useState('');
  const [tentativaCarga, setTentativaCarga] = useState(0);
  const [cargaConcluida, setCargaConcluida] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const enviando = useRef(false);
  const [chavePendente, setChavePendente] = useState<string | null>(null);
  const [rejeicaoConfirmada, setRejeicaoConfirmada] = useState(false);
  const [marca] = useState(contextoAtual);
  const fechar = () => { if (!enviando.current && !chavePendente) onFechar(); };

  useEffect(() => {
    if (!aberto) return;
    let ativo = true;
    Promise.all([api.get<Cliente[]>('/clientes/pesquisa'), api.get<Servico[]>('/servicos/')])
      .then(([listaClientes, listaServicos]) => {
        if (!ativo) return;
        setClientes(listaClientes.data);
        setServicos(listaServicos.data);
        setErroCarga('');
        setCargaConcluida(true);
      }).catch((falha: unknown) => {
        if (!ativo) return;
        setClientes([]);
        setServicos([]);
        setErroCarga(mensagemErro(falha, 'Não foi possível carregar clientes e serviços'));
      });
    return () => { ativo = false; };
  }, [aberto, tentativaCarga]);

  const alternarServico = (id: string) => {
  setServicosIds((atual) =>
    atual.includes(id) ? atual.filter((s) => s !== id) : [...atual, id]
  );
};
const salvar = async () => {
  if (enviando.current || !cargaConcluida || !contextoValido(marca)) return;
  if (!barbeiros.some((b) => b.id === barbeiroId)) {
    setErro('Selecione um profissional permitido para seu perfil');
    return;
  }
  if ((!imediato && (!data || !horaInicio)) || !clienteId || !barbeiroId || servicosIds.length === 0) {
    setErro(imediato ? 'Preencha cliente, barbeiro e pelo menos um serviço' : 'Preencha cliente, barbeiro, horário e pelo menos um serviço');
    return;
  }

  const minutos = duracao ? Number(duracao) : undefined;
  if (minutos !== undefined && (!Number.isInteger(minutos) || minutos < 1 || minutos > 480)) {
    setErro('Informe uma duração inteira entre 1 e 480 minutos');
    return;
  }
  const chave = chavePendente ?? crypto.randomUUID();
  enviando.current = true;
  setErro('');
  setRejeicaoConfirmada(false);
  setSalvando(true);
  try {
    const { data: reserva } = await api.post<{ id: string; data: string }>(imediato ? '/agendamentos/encaixes' : '/agendamentos', {
      chave_idempotencia: chave,
      filial_id: marca.filialId ?? undefined,
      cliente_id: clienteId,
      barbeiro_id: barbeiroId,
      ...(imediato ? {} : { data, hora_inicio: `${horaInicio}:00` }),
      duracao_min: minutos,
      servicos: servicosIds.map((id) => ({ servico_id: id })),
    });
    if (!contextoValido(marca)) return;
    if (!reserva?.id || !reserva.data) throw new axios.AxiosError('Confirmação incompleta');
    onSalvo(reserva.data, !!chavePendente);
  } catch (e: unknown) {
    if (!contextoValido(marca)) return;
    const incerto = escritaAgendaIncerta(e);
    if (incerto) setChavePendente(chave);
    const status = axios.isAxiosError(e) ? e.response?.status : undefined;
    const rejeitado = [400, 409, 422].includes(status ?? 0);
    setRejeicaoConfirmada(!!chavePendente && rejeitado);
    setErro(incerto ? '' : mensagemErro(e, chavePendente
      ? 'Não foi possível confirmar a solicitação anterior.'
      : 'O agendamento foi rejeitado. Revise os dados e tente novamente.'));
    if (incerto || deveConferirRegistros(e)) onConferir?.(imediato ? new Intl.DateTimeFormat('sv-SE', { timeZone: 'America/Recife' }).format(new Date()) : data);
  } finally {
    enviando.current = false;
    setSalvando(false);
  }
};
  if (!aberto) return null;

    return (
    <div className="modal-overlay" onClick={fechar}>
      <div className="modal-box" role="dialog" aria-modal="true" aria-labelledby="novo-agendamento-titulo" onClick={(e) => e.stopPropagation()}>
        <h2 id="novo-agendamento-titulo" className="modal-titulo">{imediato ? 'Iniciar atendimento agora' : 'Novo agendamento'}</h2>

        <fieldset disabled={!cargaConcluida || salvando || (!!chavePendente && !rejeicaoConfirmada)} className="agenda-formulario-campos">
        <legend>Dados do atendimento</legend>
        <label className="modal-campo">
          Cliente
          <select value={clienteId} onChange={(e) => setClienteId(e.target.value)}>
            <option value="">Selecione...</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome} - {c.telefone}
              </option>
            ))}
          </select>
        </label>

        <label className="modal-campo">
          Barbeiro
          <select value={barbeiroId} onChange={(e) => setBarbeiroId(e.target.value)}>
            <option value="">Selecione...</option>
            {barbeiros.map((b) => (
              <option key={b.id} value={b.id}>
                {b.nome}
              </option>
            ))}
          </select>
        </label>

        {!imediato && <div className="modal-linha">
          <label className="modal-campo">
            Data
            <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </label>
          <label className="modal-campo">
            Horário
            <input
              type="time"
              step={300}
              value={horaInicio}
              onChange={(e) => setHoraInicio(e.target.value)}
            />
          </label>
        </div>}

        <fieldset className="modal-servicos">
          <legend>Serviços</legend>
          {servicos.map((s) => (
            <label key={s.id} className="modal-servico-item">
              <input
                type="checkbox"
                checked={servicosIds.includes(s.id)}
                onChange={() => alternarServico(s.id)}
              />
              <span>{s.nome}</span>
              <small>{s.tempo_estimado} min</small>
            </label>
          ))}
        </fieldset>

        <label className="modal-campo">Duração total em minutos (opcional)
          <input type="number" min={1} max={480} step={1} value={duracao} onChange={e => setDuracao(e.target.value)} />
        </label>
        </fieldset>
        {!cargaConcluida && !erroCarga && <p role="status">Carregando clientes e serviços…</p>}
        {erroCarga && <><p role="alert" className="modal-erro">{erroCarga}</p>
          <button type="button" onClick={() => { setErroCarga(''); setTentativaCarga(n => n + 1); }}>Tentar carregar novamente</button></>}
        {erro && <p role="alert" className="modal-erro">{erro}</p>}
        {chavePendente && <p role="status">{rejeicaoConfirmada
          ? 'O envio mais recente foi rejeitado. Você pode corrigir os dados. Se o primeiro envio tiver sido concluído, a Agenda exibirá esse atendimento.'
          : 'O resultado ainda não foi confirmado. Tente confirmar a mesma solicitação sem criar outro atendimento.'}</p>}
        {salvando && <p role="status">{chavePendente ? 'Verificando solicitação…' : 'Salvando atendimento…'}</p>}

        <div className="modal-acoes">
          <button type="button" className="modal-btn-cancelar" disabled={salvando} onClick={() => {
            if (!chavePendente || window.confirm('O resultado continua incerto. Confira a agenda antes de criar outro atendimento. Fechar este formulário?')) onFechar();
          }}>
            {chavePendente ? 'Fechar e conferir agenda' : 'Cancelar'}
          </button>
          <button type="button" className="modal-btn-salvar" disabled={salvando || !cargaConcluida} onClick={salvar}>
            {rejeicaoConfirmada ? 'Tentar com os dados revisados' : chavePendente ? 'Confirmar mesma solicitação' : imediato ? 'Iniciar atendimento' : 'Salvar'}
          </button>
        </div>
      </div>
    </div>
  );
}
