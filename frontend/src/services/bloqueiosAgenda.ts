import api from './api';

export interface RascunhoBloqueio {
  barbeiro_id: string;
  hora_inicio: string;
  hora_fim: string;
  motivo: string;
}

export interface Bloqueio extends RascunhoBloqueio {
  id: string;
  revogado_em: string | null;
}

export type OperacaoBloqueio = { tipo: 'criar'; chave: string } | { tipo: 'remover'; id: string };
export interface EstadoBloqueio {
  rascunho: RascunhoBloqueio;
  operacao: OperacaoBloqueio | null;
}

const caminho = '/agendamentos/bloqueios';
export const chaveBloqueios = (usuario: string, filial: string, data: string) =>
  `relaxabarber:agenda:bloqueio:${usuario}:${filial}:${data}`;

export function lerEstadoBloqueio(chave: string, inicial: EstadoBloqueio): EstadoBloqueio {
  const raw = sessionStorage.getItem(chave);
  if (!raw) return inicial;
  const estado = JSON.parse(raw);
  const rascunho = estado?.rascunho;
  const operacao = estado?.operacao;
  const uuid = (id: unknown) => typeof id === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id);
  if (!rascunho || !Object.keys(inicial.rascunho).every(campo => typeof rascunho[campo] === 'string') ||
      !(operacao === null || (operacao?.tipo === 'criar' && uuid(operacao.chave)) ||
        (operacao?.tipo === 'remover' && uuid(operacao.id)))) {
    throw new Error('Dados de recuperação inválidos');
  }
  return { rascunho, operacao };
}

export async function listarBloqueios(filialId: string, data: string, signal: AbortSignal) {
  return (await api.get<Bloqueio[]>(caminho, { params: { filial_id: filialId, data }, signal })).data;
}

export async function enviarBloqueio(filialId: string, data: string, rascunho: RascunhoBloqueio, operacao: OperacaoBloqueio) {
  if (operacao.tipo === 'criar') {
    return (await api.post<Bloqueio>(caminho, { ...rascunho, motivo: rascunho.motivo.trim(), data, filial_id: filialId },
      { headers: { 'Idempotency-Key': operacao.chave } })).data;
  }
  await api.delete(`${caminho}/${operacao.id}`, { params: { filial_id: filialId } });
}

export async function conferirBloqueio(filialId: string, operacao: OperacaoBloqueio) {
  const recurso = operacao.tipo === 'criar' ? `cadastros/${operacao.chave}` : operacao.id;
  return (await api.get<Bloqueio>(`${caminho}/${recurso}`, { params: { filial_id: filialId } })).data;
}
