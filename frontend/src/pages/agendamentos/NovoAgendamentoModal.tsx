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
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onFechar}
    >
      <div
        style={{ background: '#161b22', padding: 24, borderRadius: 8, minWidth: 400 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2>Novo agendamento</h2>

        <label>
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
        <label>
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
        <label>
        Data
        <input type="date" value={data} onChange={(e) => setData(e.target.value)} />
        </label>

        <label>
          Horário
          <input
            type="time"
            step={300}
            value={horaInicio}
            onChange={(e) => setHoraInicio(e.target.value)}
          />
        </label>
        <fieldset>
          <legend>Serviços</legend>
          {servicos.map((s) => (
            <label key={s.id} style={{ display: 'block' }}>
              <input
                type="checkbox"
                checked={servicosIds.includes(s.id)}
                onChange={() => alternarServico(s.id)}
              />
              {s.nome} ({s.tempo_estimado} min)
            </label>
          ))}
        </fieldset>
        {erro && <p style={{ color: '#ff6b6b' }}>{erro}</p>}
        <button type="button" onClick={salvar}>Salvar</button>
        <button type="button" onClick={onFechar}>Cancelar</button>
      </div>
    </div>
  );
}