import { useState, useEffect, useRef } from 'react';
import api from '../../services/api';
import { mensagemErro, deveConferirRegistros, escritaIncerta } from '../../services/erros';

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
  dataInicial: string;
  onFechar: () => void;
  onSalvo: (data: string) => void;
  onConferir?: (data: string) => void;
  barbeiros: Barbeiro[];
}

export function NovoAgendamentoModal({ aberto, onFechar, onSalvo,barbeiros, dataInicial, onConferir }: Props) {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [clienteId, setClienteId] = useState('');
  const [barbeiroId, setBarbeiroId] = useState('');
  const [data, setData] = useState(dataInicial);
  const [horaInicio, setHoraInicio] = useState('');
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [servicosIds, setServicosIds] = useState<string[]>([]);
  const [erro, setErro] = useState('');
  const [erroCarga, setErroCarga] = useState('');
  const [salvando, setSalvando] = useState(false);
  const enviando = useRef(false);
  const [resultadoIncerto, setResultadoIncerto] = useState(false);
  const fechar = () => { if (!enviando.current) onFechar(); };

  useEffect(() => {
    if (!aberto) return;
    let ativo = true;
    Promise.all([api.get<Cliente[]>('/clientes/pesquisa'), api.get<Servico[]>('/servicos/')])
      .then(([listaClientes, listaServicos]) => {
        if (!ativo) return;
        setClientes(listaClientes.data);
        setServicos(listaServicos.data);
        setErroCarga('');
      }).catch((falha: unknown) => {
        if (!ativo) return;
        setClientes([]);
        setServicos([]);
        setErroCarga(mensagemErro(falha, 'Não foi possível carregar clientes e serviços. Feche e tente novamente'));
      });
    return () => { ativo = false; };
  }, [aberto]);

  const alternarServico = (id: string) => {
  setServicosIds((atual) =>
    atual.includes(id) ? atual.filter((s) => s !== id) : [...atual, id]
  );
};
const salvar = async () => {
  if (enviando.current || erroCarga || resultadoIncerto) return;
  if (!barbeiros.some((b) => b.id === barbeiroId)) {
    setErro('Selecione um profissional permitido para seu perfil');
    return;
  }
  if (!data || !clienteId || !barbeiroId || !horaInicio || servicosIds.length === 0) {
    setErro('Preencha cliente, barbeiro, horário e pelo menos um serviço');
    return;
  }

  enviando.current = true;
  setErro('');
  setSalvando(true);
  try {
    await api.post('/agendamentos', {
      cliente_id: clienteId,
      barbeiro_id: barbeiroId,
      data,
      hora_inicio: `${horaInicio}:00`,
      servicos: servicosIds.map((id) => ({ servico_id: id })),
    });
    setErro('');
    setClienteId('');
    setBarbeiroId('');
    setHoraInicio('');
    setServicosIds([]);
    onSalvo(data);
  } catch (e: unknown) {
    const incerto = escritaIncerta(e);
    setResultadoIncerto(incerto);
    setErro(mensagemErro(e, 'Erro ao salvar o agendamento') + (incerto ? ' Confira a agenda antes de tentar criar novamente.' : ''));
    if (deveConferirRegistros(e)) onConferir?.(data);
  } finally {
    enviando.current = false;
    setSalvando(false);
  }
};
  if (!aberto) return null;

    return (
    <div className="modal-overlay" onClick={fechar}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-titulo">Novo agendamento</h2>

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

        <div className="modal-linha">
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
        </div>

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

        {erroCarga && <p role="alert" className="modal-erro">{erroCarga}</p>}
        {erro && <p role="alert" className="modal-erro">{erro}</p>}
        {resultadoIncerto && <p>Feche este formulário e confira a agenda. O envio não será repetido automaticamente.</p>}

        <div className="modal-acoes">
          <button type="button" className="modal-btn-cancelar" disabled={salvando} onClick={fechar}>
            Cancelar
          </button>
          <button type="button" className="modal-btn-salvar" disabled={salvando || !!erroCarga || resultadoIncerto} onClick={salvar}>
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}