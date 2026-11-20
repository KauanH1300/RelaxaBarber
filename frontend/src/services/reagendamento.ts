import axios from 'axios';
import api from './api';
import { contextoAtual, contextoValido } from './filialAtiva';
import type { MarcaContexto } from './filialAtiva';
import { obterToken } from './sessao';
import { podeOperarAgenda } from './permissoesAgenda';
import type { UsuarioAgenda } from './permissoesAgenda';

export interface ReservaReagendamento {
  id: string; filial_id: string; data: string; hora_inicio: string; hora_fim: string;
  barbeiro_id: string; status: string; atualizado_em: string | null;
  cliente: { nome: string }; barbeiro: { id: string; nome: string };
}
export interface HistoricoReagendamento {
  registrado_por?: string | null; registrado_por_cliente?: string | null;
  id: string; agendamento_id: string; registrado_em: string; motivo: string | null;
  data_anterior: string; hora_inicio_anterior: string; hora_fim_anterior?: string; barbeiro_id_anterior: string;
  data_nova: string; hora_inicio_nova: string; hora_fim_nova?: string; barbeiro_id_novo: string;
}
export interface DadosReagendamento { data: string; hora_inicio: string; barbeiro_id: string; motivo: string; duracao_min?: number }
export const podeReagendar = (usuario: UsuarioAgenda | null, barbeiroId: string, status: string) =>
  podeOperarAgenda(usuario, barbeiroId) && ['pendente', 'aguardando'].includes(status);

function conferir(marca: MarcaContexto) {
  if (!marca.token || !marca.filialId || !contextoValido(marca) || obterToken() !== marca.token) {
    throw new axios.CanceledError('A filial ou sessão mudou. Abra o atendimento novamente.');
  }
}

export async function consultarReagendamento(id: string, marca: MarcaContexto = contextoAtual(), signal?: AbortSignal) {
  conferir(marca);
  const path = `/agendamentos/${encodeURIComponent(id)}`;
  const [reserva, historico] = await Promise.all([
    api.get<ReservaReagendamento>(path, { params: { filial_id: marca.filialId }, signal }),
    api.get<HistoricoReagendamento[]>(`${path}/reagendamentos`, { params: { filial_id: marca.filialId }, signal }),
  ]);
  conferir(marca);
  if (reserva.data.id !== id || reserva.data.filial_id !== marca.filialId || historico.data.some(h => h.agendamento_id !== id)) {
    throw new Error('Resposta incompatível com o atendimento. Consulte novamente.');
  }
  return { reserva: reserva.data, historico: historico.data };
}

export function serializarReagendamento(reserva: ReservaReagendamento, dados: DadosReagendamento, usuario: UsuarioAgenda) {
  if (!podeReagendar(usuario, reserva.barbeiro_id, reserva.status) || !podeOperarAgenda(usuario, dados.barbeiro_id)) {
    throw new Error('Sem permissão para reagendar este atendimento ou transferir o barbeiro.');
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dados.data) || Number.isNaN(Date.parse(`${dados.data}T12:00:00Z`)) ||
      new Date(`${dados.data}T12:00:00Z`).toISOString().slice(0, 10) !== dados.data ||
      !/^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?$/.test(dados.hora_inicio) || !dados.barbeiro_id) {
    throw new Error('Informe uma data, horário e barbeiro válidos.');
  }
  if (dados.motivo.length > 1000) throw new Error('O motivo deve ter até 1000 caracteres.');
  const duracao = dados.duracao_min;
  if (duracao !== undefined && (!Number.isInteger(duracao) || duracao < 1 || duracao > 480)) {
    throw new Error('Informe uma duração inteira entre 1 e 480 minutos.');
  }
  return { data: dados.data, hora_inicio: dados.hora_inicio, barbeiro_id: dados.barbeiro_id,
    ...(duracao === undefined ? {} : { duracao_min: duracao }),
    motivo: dados.motivo.trim() || null, atualizado_em_esperado: reserva.atualizado_em };
}

export async function salvarReagendamento(reserva: ReservaReagendamento, dados: DadosReagendamento,
  usuario: UsuarioAgenda, marca: MarcaContexto) {
  conferir(marca);
  if (reserva.filial_id !== marca.filialId) throw new Error('O atendimento pertence a outra filial.');
  const payload = serializarReagendamento(reserva, dados, usuario);
  const { data } = await api.patch<ReservaReagendamento>(`/agendamentos/${encodeURIComponent(reserva.id)}/reagendamento`,
    payload, { params: { filial_id: marca.filialId } });
  conferir(marca);
  if (data.id !== reserva.id || data.filial_id !== marca.filialId) throw new Error('Resposta de salvamento inconsistente. Confira a agenda.');
  return data;
}
