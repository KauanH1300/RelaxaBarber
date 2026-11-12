import assert from 'node:assert/strict';
import test from 'node:test';
import axios from 'axios';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { carregarTs } from './helpers/carregarTs.mjs';

globalThis.localStorage = { getItem: () => 'jwt-horarios' };
globalThis.window = new EventTarget();
const h = await carregarTs('services/horarios.ts');
const { default: api } = await carregarTs('services/api.ts');
const contexto = await carregarTs('services/filialAtiva.ts');
const { SemanaExpediente } = await carregarTs('pages/horarios/SemanaExpediente.tsx');
const admin = { perfil: 'admin', ativo: true };
const semana = () => h.semanaInicial().map((d) => ({ ...d, hora_inicio: '08:00', hora_fim: '18:00' }));
const resposta = (dias = semana()) => ({ filial_id: 'filial-a', configurado: true, dias });
function iniciar() { contexto.mudarContexto('jwt-horarios', 'filial-a'); }

test('semana não configurada mantém sete dias em branco, sem supor fechamento', () => {
  const dias = h.diasDaResposta({ filial_id: 'filial-a', configurado: false, dias: [] });
  assert.equal(dias.length, 7);
  assert.deepEqual(dias.map((d) => d.dia_semana), [0, 1, 2, 3, 4, 5, 6]);
  assert.ok(dias.every((d) => !d.fechado && d.hora_inicio === '' && d.hora_fim === ''));
  assert.throws(() => h.serializarHorarios(dias));
});
test('serializa dias ordenados e somente campos do schema', () => {
  const dias = semana().reverse().map((d) => ({ ...d, campoExtra: 'ignorar' }));
  const payload = h.serializarHorarios(dias);
  assert.deepEqual(payload.dias.map((d) => d.dia_semana), [0, 1, 2, 3, 4, 5, 6]);
  assert.deepEqual(Object.keys(payload.dias[0]), ['dia_semana', 'fechado', 'hora_inicio', 'hora_fim']);
});
test('dias fechados enviam null mesmo que o rascunho contenha horários', () => {
  const dias = semana(); dias[6].fechado = true;
  assert.deepEqual(h.serializarHorarios(dias).dias[6], { dia_semana: 6, fechado: true, hora_inicio: null, hora_fim: null });
  dias[6].hora_inicio = null; dias[6].hora_fim = null;
  assert.doesNotThrow(() => h.serializarHorarios(dias));
});
test('rejeita semana incompleta, duplicação, booleano como dia e intervalos inválidos', () => {
  assert.throws(() => h.serializarHorarios(semana().slice(0, 6)));
  for (const change of [{ dia_semana: 1 }, { dia_semana: true }, { dia_semana: 7 }, { fechado: 'false' }, { hora_inicio: '' }, { hora_inicio: null }, { hora_inicio: '18:00' }, { hora_inicio: '19:00' }, { hora_fim: '24:00' }, { hora_inicio: '08:00+03:00' }]) {
    const dias = semana(); Object.assign(dias[0], change);
    assert.throws(() => h.serializarHorarios(dias));
  }
});
test('preserva precisão dos horários retornados pelo backend', () => {
  const dias = semana(); dias[0].hora_inicio = '08:00:00.123456'; dias[0].hora_fim = '08:00:00.123457';
  assert.equal(h.diasDaResposta(resposta(dias))[0].hora_inicio, '08:00:00.123456');
});
test('somente ADMIN ativo pode editar e salvar; outros perfis não enviam requisição', async () => {
  iniciar(); let calls = 0;
  api.defaults.adapter = async () => { calls++; throw new Error('Não deveria enviar'); };
  for (const user of [{ perfil: 'recepcao', ativo: true }, { perfil: 'barbeiro', ativo: true }, { perfil: 'barbeiro_chefe', ativo: true }, { perfil: 'admin', ativo: false }]) {
    assert.equal(h.podeEditarHorarios(user), false);
    await assert.rejects(h.salvarHorarios('filial-a', semana(), user));
  }
  assert.equal(h.podeEditarHorarios(admin), true); assert.equal(calls, 0);
});
test('GET e PUT usam rota, token e payload reais, sem filial_id no corpo', async () => {
  iniciar(); const requests = [];
  api.defaults.adapter = async (config) => { requests.push(config); return { config, status: 200, headers: {}, data: resposta() }; };
  await h.consultarHorarios('filial-a'); await h.salvarHorarios('filial-a', semana(), admin);
  assert.equal(requests[0].url, '/filiais/filial-a/horarios');
  assert.equal(requests[1].method, 'put'); assert.equal(requests[1].headers.Authorization, 'Bearer jwt-horarios');
  assert.deepEqual(JSON.parse(requests[1].data), { dias: semana() });
});
test('validação local e contexto incorreto impedem envio', async () => {
  iniciar(); let calls = 0; api.defaults.adapter = async () => { calls++; throw new Error(); };
  await assert.rejects(h.salvarHorarios('filial-a', h.semanaInicial(), admin));
  await assert.rejects(h.consultarHorarios('filial-b'), axios.isCancel);
  assert.equal(calls, 0);
});
test('resposta tardia de outra filial é descartada', async () => {
  iniciar(); let release; let started;
  const waiting = new Promise((r) => { started = r; });
  api.defaults.adapter = (config) => new Promise((resolve) => { release = () => resolve({ config, status: 200, headers: {}, data: resposta() }); started(); });
  const request = h.consultarHorarios('filial-a'); await waiting;
  contexto.mudarContexto('jwt-horarios', 'filial-b'); release();
  await assert.rejects(request, axios.isCancel);
});
for (const status of [401, 403, 404, 409, 422]) {
  test(`erro HTTP ${status} é propagado e apresentado`, async () => {
    iniciar();
    const error = new axios.AxiosError('erro', undefined, { url: '/filiais/filial-a/horarios' }, undefined, { status, data: {}, headers: {} });
    api.defaults.adapter = async () => { throw error; };
    await assert.rejects(h.salvarHorarios('filial-a', semana(), admin), (e) => e === error);
    assert.match(h.erroHorarios(error), { 401: /Sessão expirada/, 403: /Sem permissão/, 404: /Filial não encontrada/, 409: /conflita/, 422: /Revise os sete/ }[status]);
  });
}
test('detalhe de conflito e erros de validação do backend são preservados', () => {
  for (const [status, detail] of [[409, 'Expediente incompatível com a reserva'], [422, [{ msg: 'Informe os sete dias' }]]]) {
    const error = new axios.AxiosError('erro', undefined, {}, undefined, { status, data: { detail } });
    assert.match(h.erroHorarios(error), status === 409 ? /incompatível/ : /sete dias/);
  }
  assert.match(h.erroHorarios(new axios.AxiosError('timeout'), true), /incerto/);
  assert.doesNotMatch(h.erroHorarios(new axios.AxiosError('timeout')), /incerto/);
});
test('rascunhos incompletos sobrevivem à navegação e são separados por usuário e filial', () => {
  const dias = h.semanaInicial(); dias[1].fechado = true;
  assert.deepEqual(h.lerRascunho(JSON.stringify(dias)), dias);
  assert.equal(h.lerRascunho('{invalid'), null);
  assert.equal(h.lerRascunho(JSON.stringify([{}])), null);
  assert.notEqual(h.chaveRascunho('a', '1'), h.chaveRascunho('a', '2'));
  assert.notEqual(h.chaveRascunho('a', '1'), h.chaveRascunho('b', '1'));
});
test('formulário exibe sete dias, bloqueia leitura e omite inputs de dia fechado', () => {
  const dias = semana(); dias[6].fechado = true;
  const render = (editavel) => renderToStaticMarkup(createElement(SemanaExpediente, { dias, editavel, ocupado: false, alterar() {} }));
  const leitura = render(false); const edicao = render(true);
  assert.equal((leitura.match(/<fieldset/g) ?? []).length, 7);
  assert.equal((leitura.match(/<fieldset[^>]*disabled/g) ?? []).length, 7);
  assert.equal((edicao.match(/<fieldset[^>]*disabled/g) ?? []).length, 0);
  assert.equal((edicao.match(/type="time"/g) ?? []).length, 12);
  assert.ok(edicao.indexOf('Segunda-feira') < edicao.indexOf('Domingo'));
  assert.match(edicao, /Sem atendimento/);
});
