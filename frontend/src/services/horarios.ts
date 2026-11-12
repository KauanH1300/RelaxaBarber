import axios from 'axios';
import api from './api';
import { contextoAtual, contextoValido } from './filialAtiva';
import { obterToken } from './sessao';
import { mensagemErro, escritaIncerta } from './erros';
import type { UsuarioLogado } from './usuario';

export const DIAS_SEMANA = ['Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo'];
export interface DiaHorario { dia_semana: number; fechado: boolean; hora_inicio: string | null; hora_fim: string | null }
export interface SemanaHorario { filial_id: string; configurado: boolean; dias: DiaHorario[] }
export const podeEditarHorarios = (usuario: Pick<UsuarioLogado, 'perfil' | 'ativo'>) => usuario.ativo && usuario.perfil === 'admin';

export function semanaInicial(): DiaHorario[] {
  return DIAS_SEMANA.map((_, dia_semana) => ({ dia_semana, fechado: false, hora_inicio: '', hora_fim: '' }));
}

function horarioValido(value: unknown): value is string {
  return typeof value === 'string' && /^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?$/.test(value);
}
function segundos(value: string): number {
  const [h, m, s = '0'] = value.split(':');
  return Number(h) * 3600 + Number(m) * 60 + Number(s);
}
export function serializarHorarios(dias: DiaHorario[]): { dias: DiaHorario[] } {
  if (dias.length !== 7 || new Set(dias.map((d) => d.dia_semana)).size !== 7 || dias.some((d) => !Number.isInteger(d.dia_semana) || d.dia_semana < 0 || d.dia_semana > 6)) {
    throw new Error('Informe os sete dias da semana, sem repetição.');
  }
  return { dias: [...dias].sort((a, b) => a.dia_semana - b.dia_semana).map((d) => {
    if (typeof d.fechado !== 'boolean') throw new Error('Informe se cada dia está aberto ou fechado.');
    if (d.fechado) return { dia_semana: d.dia_semana, fechado: true, hora_inicio: null, hora_fim: null };
    if (!horarioValido(d.hora_inicio) || !horarioValido(d.hora_fim) || segundos(d.hora_inicio) >= segundos(d.hora_fim)) {
      throw new Error(`${DIAS_SEMANA[d.dia_semana]}: informe abertura e fechamento válidos, com abertura anterior ao fechamento no mesmo dia.`);
    }
    return { dia_semana: d.dia_semana, fechado: false, hora_inicio: d.hora_inicio, hora_fim: d.hora_fim };
  }) };
}

export function diasDaResposta(semana: SemanaHorario): DiaHorario[] {
  if (!semana.configurado) {
    if (semana.dias.length) throw new Error('Resposta de expediente inconsistente. Atualize a página.');
    return semanaInicial();
  }
  return serializarHorarios(semana.dias).dias;
}

function validarContexto(filialId: string) {
  const marca = contextoAtual();
  if (!marca.token || marca.token !== obterToken() || marca.filialId !== filialId) throw new axios.CanceledError('A filial ou sessão mudou.');
  return () => {
    if (!contextoValido(marca) || obterToken() !== marca.token) throw new axios.CanceledError('Resposta de outra filial descartada.');
  };
}
export async function consultarHorarios(filialId: string, signal?: AbortSignal): Promise<SemanaHorario> {
  const conferir = validarContexto(filialId);
  try {
    const { data } = await api.get<SemanaHorario>(`/filiais/${encodeURIComponent(filialId)}/horarios`, { signal });
    conferir();
    if (data.filial_id !== filialId) throw new Error('Resposta de outra filial.');
    diasDaResposta(data);
    return data;
  } catch (erro) { conferir(); throw erro; }
}
export async function salvarHorarios(filialId: string, dias: DiaHorario[], usuario: Pick<UsuarioLogado, 'perfil' | 'ativo'>): Promise<SemanaHorario> {
  if (!podeEditarHorarios(usuario)) throw new Error('Somente administradores ativos podem editar o expediente.');
  const conferir = validarContexto(filialId);
  const payload = serializarHorarios(dias);
  try {
    const { data } = await api.put<SemanaHorario>(`/filiais/${encodeURIComponent(filialId)}/horarios`, payload);
    conferir();
    if (data.filial_id !== filialId || !data.configurado) throw new Error('Resposta de salvamento inconsistente. Confira o expediente.');
    diasDaResposta(data);
    return data;
  } catch (erro) { conferir(); throw erro; }
}

export function erroHorarios(erro: unknown, salvamento = false): string {
  const status = axios.isAxiosError(erro) ? erro.response?.status : undefined;
  const fallback = status === 404 ? 'Filial não encontrada. Atualize as unidades.'
    : status === 409 ? 'O expediente conflita com agendamentos. Revise os horários.'
    : status === 422 ? 'Revise os sete dias e os intervalos informados.' : 'Não foi possível concluir a operação';
  return mensagemErro(erro, fallback) + (salvamento && escritaIncerta(erro) ? ' O resultado do salvamento pode ser incerto. Confira a semana salva antes de tentar novamente.' : '');
}

export function chaveRascunho(usuarioId: string, filialId: string): string {
  return `relaxabarber:horarios:${usuarioId}:${filialId}`;
}
export function lerRascunho(raw: string | null): DiaHorario[] | null {
  try {
    const dias: DiaHorario[] = JSON.parse(raw ?? 'null');
    if (!Array.isArray(dias) || dias.length !== 7) return null;
    if (dias.some((d, i) => !d || d.dia_semana !== i || typeof d.fechado !== 'boolean' || ![d.hora_inicio, d.hora_fim].every((h) => h === null || typeof h === 'string'))) return null;
    return dias;
  } catch { return null; }
}
