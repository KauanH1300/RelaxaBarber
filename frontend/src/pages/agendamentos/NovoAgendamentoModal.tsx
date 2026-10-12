import { useState, useEffect } from 'react';
import api from '../../services/api';

interface Cliente {
  id: string;
  nome: string;
  telefone: string;
}
interface Barbeiro {
  id: string;
  nome: string;
}
interface Props {
  aberto: boolean;
  onFechar: () => void;
  barbeiros: Barbeiro[];
}
interface Servico {
  id: string;
  nome: string;
  preco: string;
  tempo_estimado: number;
}
interface Props {
  aberto: boolean;
  onFechar: () => void;
  onSalvo: () => void;
  barbeiros: Barbeiro[];
}

export function NovoAgendamentoModal({ aberto, onFechar, onSalvo,barbeiros }: Props) {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [clienteId, setClienteId] = useState('');
  const [barbeiroId, setBarbeiroId] = useState('');
  const [data, setData] = useState(new Date().toLocaleDateString('en-CA'));
  const [horaInicio, setHoraInicio] = useState('');
  const [servicos, setServicos] = useState<Servico[]>([]);
  const [servicosIds, setServicosIds] = useState<string[]>([]);
  const [erro, setErro] = useState('');

  useEffect(() => {
    if (!aberto) return;
    api
      .get<Cliente[]>('/clientes')
      .then((r) => setClientes(r.data))
      .catch(() => setClientes([]));
    api
      .get<Servico[]>('/servicos')
      .then((r) => setServicos(r.data))
      .catch(() => setServicos([]));
  }, [aberto]);

  const alternarServico = (id: string) => {
  setServicosIds((atual) =>
    atual.includes(id) ? atual.filter((s) => s !== id) : [...atual, id]
  );
};
const salvar = async () => {
  if (!clienteId || !barbeiroId || !horaInicio || servicosIds.length === 0) {
    setErro('Preencha cliente, barbeiro, horário e pelo menos um serviço');
    return;
  }

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
    onSalvo();
  } catch (e: any) {
    setErro(e.response?.data?.detail ?? 'Erro ao salvar o agendamento');
  }
};
  if (!aberto) return null;

    return (
    <div className="modal-overlay" onClick={onFechar}>
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

        {erro && <p className="modal-erro">{erro}</p>}

        <div className="modal-acoes">
          <button type="button" className="modal-btn-cancelar" onClick={onFechar}>
            Cancelar
          </button>
          <button type="button" className="modal-btn-salvar" onClick={salvar}>
            Salvar
          </button>
        </div>
      </div>
    </div>
  );
}