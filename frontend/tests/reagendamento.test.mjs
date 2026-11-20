import test from 'node:test';
import assert from 'node:assert/strict';
import axios from 'axios';
import { carregarTs } from './helpers/carregarTs.mjs';

const storage = new Map([['token', 'token-ficticio']]);
globalThis.localStorage = { getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k) };
globalThis.window = new EventTarget();
const r = await carregarTs('services/reagendamento.ts');
const { mudarContexto } = await carregarTs('services/filialAtiva.ts');
const api = (await carregarTs('services/api.ts')).default;
const admin = { id: 'admin', perfil: 'admin' };
const reserva = { id: 'reserva', filial_id: 'filial', data: '2099-01-01', hora_inicio: '09:00:00', hora_fim: '09:30:00',
  barbeiro_id: 'barbeiro', status: 'pendente', atualizado_em: '2026-11-16T10:00:00.123456Z' };
const dados = { data: '2099-01-02', hora_inicio: '11:00', barbeiro_id: 'outro', motivo: '  Cliente pediu  ' };
const iniciar = () => mudarContexto('token-ficticio', 'filial');

test('permissão considera profissional e estado do atendimento', () => {
  for (const perfil of ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe']) {
    const usuario = { id: 'barbeiro', perfil };
    for (const status of ['pendente', 'aguardando', 'em_atendimento', 'cancelado', 'concluido']) {
      assert.equal(r.podeReagendar(usuario, 'barbeiro', status), ['pendente','aguardando'].includes(status));
      assert.equal(r.podeReagendar(usuario, 'outro', status), ['admin','recepcao'].includes(perfil) && ['pendente','aguardando'].includes(status));
    }
  }
});

test('envia somente os campos permitidos e mantém precisão da versão', async () => {
  const marca = iniciar(); let chamada;
  api.defaults.adapter = async config => { chamada = config; return { status: 200, data: { ...reserva, ...dados }, config }; };
  await r.salvarReagendamento(reserva, { ...dados, cliente_id: 'proibido', valor_total: 999 }, admin, marca);
  assert.equal(chamada.url, '/agendamentos/reserva/reagendamento');
  assert.equal(chamada.params.filial_id, 'filial');
  assert.deepEqual(JSON.parse(chamada.data), { ...dados, motivo: 'Cliente pediu', atualizado_em_esperado: reserva.atualizado_em });
});

test('envia duração personalizada somente se informada e válida', () => {
  assert.equal(r.serializarReagendamento(reserva, { ...dados, duracao_min: 45 }, admin).duracao_min, 45);
  assert.ok(!('duracao_min' in r.serializarReagendamento(reserva, dados, admin)));
  for (const duracao_min of [0, 15.5, 481]) {
    assert.throws(() => r.serializarReagendamento(reserva, { ...dados, duracao_min }, admin), /duração/);
  }
});

test('entradas inválidas e transferência sem permissão não fazem requisições', async () => {
  const marca = iniciar(); let calls = 0;
  api.defaults.adapter = async () => { calls++; throw new Error('Não deveria enviar'); };
  for (const change of [{ data:'2099-02-31' }, { data:'' }, { hora_inicio:'24:00' }, { hora_inicio:'12:00+03:00' }, { motivo:'a'.repeat(1001) }]) {
    await assert.rejects(r.salvarReagendamento(reserva, { ...dados, ...change }, admin, marca));
  }
  await assert.rejects(r.salvarReagendamento(reserva, dados, { id:'barbeiro', perfil:'barbeiro' }, marca), /permissão/);
  assert.equal(calls, 0);
});

test('formulário de outra filial ou sessão não grava', async () => {
  const marca = iniciar(); let calls = 0;
  api.defaults.adapter = async () => { calls++; throw new Error('Não deveria enviar'); };
  mudarContexto('token-ficticio', 'outra');
  await assert.rejects(r.salvarReagendamento(reserva, dados, admin, marca), axios.isCancel);
  assert.equal(calls, 0);
});

test('consulta reúne reserva e histórico da filial e descarta resposta tardia', async () => {
  let marca = iniciar();
  api.defaults.adapter = async config => ({ status:200, data: config.url.endsWith('/reagendamentos') ? [] : reserva, config });
  assert.deepEqual(await r.consultarReagendamento('reserva', marca), { reserva, historico: [] });
  marca = iniciar();
  api.defaults.adapter = async config => { mudarContexto('token-ficticio', 'outra'); return { status:200, data:reserva, config }; };
  await assert.rejects(r.consultarReagendamento('reserva', marca), axios.isCancel);
});

for (const status of [403, 404, 409, 422, 503]) test(`preserva erro HTTP ${status} sem repetir escrita`, async () => {
  const marca = iniciar(); let calls = 0;
  api.defaults.adapter = async config => { calls++; throw new axios.AxiosError('falha', undefined, config, null, { status, data:{ detail:'Conflito seguro' }, config }); };
  await assert.rejects(r.salvarReagendamento(reserva, dados, admin, marca), e => e.response?.status === status);
  assert.equal(calls, 1);
});
