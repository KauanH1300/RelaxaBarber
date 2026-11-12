import assert from 'node:assert/strict';
import test from 'node:test';
import axios from 'axios';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { carregarTs } from './helpers/carregarTs.mjs';

globalThis.localStorage = { getItem: () => 'jwt-teste' };
globalThis.window = new EventTarget();
const { prepararCliente, salvarCliente, consultarCliente, listarClientes, podeGerenciarClientes, erroCliente, chaveRascunhoCliente, serializarRascunhoCliente, lerRascunhoCliente, dadosClienteVazios, dadosClienteAlterados } = await carregarTs('services/clientes.ts');
const { default: api } = await carregarTs('services/api.ts');
const contexto = await carregarTs('services/filialAtiva.ts');
const { FormCliente } = await carregarTs('pages/unidade/FormCliente.tsx');
const { DadosCadastraisCliente } = await carregarTs('pages/unidade/DetalheCliente.tsx');
const dados = { nome: ' Ana Silva ', telefone: ' +55 (81) 99999-9999 ', email: ' ana@example.com ' };

test('normaliza bordas, preserva telefone e permite remover email', () => {
  assert.deepEqual(prepararCliente(dados), { nome: 'Ana Silva', telefone: '+55 (81) 99999-9999', email: 'ana@example.com' });
  assert.equal(prepararCliente({ ...dados, email: ' ' }).email, null);
});

test('rejeita obrigatórios vazios, limites do banco e email inválido', () => {
  for (const changes of [{ nome: ' ' }, { telefone: '' }, { nome: 'a'.repeat(151) }, { telefone: '1'.repeat(21) }, { email: 'invalido' }, { email: 'a@b' }, { email: 'a'.repeat(250) + '@exemplo.com' }]) {
    assert.throws(() => prepararCliente({ ...dados, ...changes }));
  }
  assert.doesNotThrow(() => prepararCliente({ nome: 'a'.repeat(150), telefone: '1'.repeat(20), email: '' }));
});

test('cadastro e edição enviam somente campos permitidos e filial correta', async () => {
  contexto.mudarContexto('jwt-teste', 'filial-a');
  const requests = [];
  api.defaults.adapter = async (config) => {
    requests.push(config);
    return { status: 200, data: { id: 'cliente', ...JSON.parse(config.data) }, headers: {}, config };
  };
  await salvarCliente(dados, 'filial-a');
  await salvarCliente({ ...dados, email: '' }, 'filial-a', 'cliente');
  assert.equal(requests[0].method, 'post');
  assert.equal(requests[0].url, '/clientes');
  assert.equal(JSON.parse(requests[0].data).filial_id, 'filial-a');
  assert.equal(requests[1].method, 'patch');
  assert.equal(requests[1].url, '/clientes/cliente');
  assert.deepEqual(JSON.parse(requests[1].data), { nome: 'Ana Silva', telefone: '+55 (81) 99999-9999', email: null });
  assert.equal(requests[1].params.filial_id, 'filial-a');
  assert.equal(requests[1].headers.Authorization, 'Bearer jwt-teste');
});

test('erro de validação local não realiza requisição', async () => {
  let calls = 0;
  api.defaults.adapter = async () => { calls++; throw new Error('Não deveria enviar'); };
  await assert.rejects(salvarCliente({ ...dados, nome: '' }, 'filial-a'));
  assert.equal(calls, 0);
});

test('formulário antigo não grava em outra filial', async () => {
  contexto.mudarContexto('jwt-teste', 'filial-b');
  let calls = 0;
  api.defaults.adapter = async () => { calls++; throw new Error('Não deveria enviar'); };
  await assert.rejects(salvarCliente(dados, 'filial-a'), axios.isCancel);
  await assert.rejects(salvarCliente(dados, 'filial-a', 'cliente'), axios.isCancel);
  assert.equal(calls, 0);
});

test('detalhe antigo é descartado após mudança de contexto', async () => {
  contexto.mudarContexto('jwt-teste', 'filial-a');
  let release;
  let started;
  const ready = new Promise((resolve) => { started = resolve; });
  api.defaults.adapter = (config) => new Promise((resolve) => {
    release = () => resolve({ status: 200, data: { id: 'antigo' }, headers: {}, config });
    started();
  });
  const pending = consultarCliente('cliente', 'filial-a');
  await ready;
  contexto.mudarContexto('jwt-teste', 'filial-b');
  release();
  await assert.rejects(pending, axios.isCancel);
});

for (const status of [403, 404, 409, 422, 503]) {
  test(`preserva erro HTTP ${status} para feedback sem repetir escrita`, async () => {
    contexto.mudarContexto('jwt-teste', 'filial-a');
    let calls = 0;
    api.defaults.adapter = async (config) => {
      calls++;
      throw new axios.AxiosError('erro', undefined, config, undefined, { status, data: { detail: 'Falha de teste' }, headers: {}, config });
    };
    await assert.rejects(salvarCliente(dados, 'filial-a'), (e) => e.response.status === status);
    assert.equal(calls, 1);
  });
}

test('formulário apresenta campos acessíveis e bloqueia edição durante carga', () => {
  const novo = renderToStaticMarkup(createElement(FormCliente, { usuarioId: 'operador', aoCancelar() {}, aoSalvar() {} }));
  assert.match(novo, /Novo cliente/);
  assert.match(novo, /type="tel"/);
  assert.match(novo, /type="email"/);
  assert.match(novo, /maxLength="150"/);
  const editando = renderToStaticMarkup(createElement(FormCliente, { id: 'cliente', usuarioId: 'operador', aoCancelar() {}, aoSalvar() {} }));
  assert.match(editando, /Carregando cliente/);
  assert.match(editando, /fieldset disabled/);
  assert.match(editando, /cadastro é compartilhado/);
});

test('busca usa endpoint local, parâmetro busca e filial ativa', async () => {
  contexto.mudarContexto('jwt-teste', 'filial-a');
  const requests = [];
  api.defaults.adapter = async (config) => { requests.push(config); return { status: 200, data: [], headers: {}, config }; };
  assert.deepEqual(await listarClientes(' Ana '), []);
  await listarClientes(' ');
  assert.equal(requests[0].url, '/clientes');
  assert.equal(requests[0].params.busca, 'Ana');
  assert.equal(requests[0].params.filial_id, 'filial-a');
  assert.equal(requests[1].params.busca, undefined);
});

test('busca tardia não atravessa mudança de filial', async () => {
  contexto.mudarContexto('jwt-teste', 'filial-a');
  let finish, start;
  const started = new Promise((resolve) => { start = resolve; });
  api.defaults.adapter = (config) => new Promise((resolve) => { finish = () => resolve({ status: 200, data: [], headers: {}, config }); start(); });
  const pending = listarClientes('Ana'); await started;
  contexto.mudarContexto('jwt-teste', 'filial-b'); finish();
  await assert.rejects(pending, axios.isCancel);
});

test('rascunho é isolado por usuário, filial e cliente e expira em oito horas', () => {
  const base = dadosClienteVazios();
  const raw = serializarRascunhoCliente(dados, base, false, 1000);
  assert.deepEqual(lerRascunhoCliente(raw, 1000).dados, dados);
  assert.equal(lerRascunhoCliente(raw, 1000 + 8 * 60 * 60 * 1000), null);
  assert.equal(lerRascunhoCliente('{invalid'), null);
  assert.equal(lerRascunhoCliente(JSON.stringify({ dados: {}, base: {}, incerto: false, expira: Date.now() + 1000 })), null);
  assert.equal(new Set([chaveRascunhoCliente('a', '1'), chaveRascunhoCliente('b', '1'), chaveRascunhoCliente('a', '2'), chaveRascunhoCliente('a', '1', 'cliente')]).size, 4);
  assert.equal(dadosClienteAlterados(dados, { ...dados }), false);
  assert.equal(dadosClienteAlterados(dados, { ...dados, email: '' }), true);
});

test('rascunho recuperado de uma escrita incerta bloqueia repetição', () => {
  const raw = serializarRascunhoCliente(dados, dadosClienteVazios(), true);
  globalThis.sessionStorage = { getItem: () => raw };
  try {
    const html = renderToStaticMarkup(createElement(FormCliente, { usuarioId: 'operador', aoCancelar() {}, aoSalvar() {} }));
    assert.match(html, /Rascunho recuperado/);
    assert.match(html, /salvamento a conferir/);
    assert.match(html, /fieldset disabled/);
    assert.match(html, /Descartar rascunho após conferência/);
  } finally { delete globalThis.sessionStorage; }
});

for (const perfil of ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro']) {
  test(`perfil ${perfil} ativo mantém a permissão de cadastro existente`, () => {
    assert.equal(podeGerenciarClientes({ perfil, ativo: true }), true);
    assert.equal(podeGerenciarClientes({ perfil, ativo: false }), false);
  });
}
test('perfil desconhecido não habilita edição', () => {
  assert.equal(podeGerenciarClientes({ perfil: 'invalido', ativo: true }), false);
  const html = renderToStaticMarkup(createElement(FormCliente, { usuarioId: 'operador', habilitado: false, aoCancelar() {}, aoSalvar() {} }));
  assert.match(html, /fieldset disabled/);
});
test('conflito 409 orienta sem expor detalhes de outras filiais', () => {
  const error = new axios.AxiosError('erro', undefined, {}, undefined, { status: 409, data: { detail: 'Cliente privado de outra filial' } });
  const mensagem = erroCliente(error, 'Falha');
  assert.match(mensagem, /Já existe um cadastro/);
  assert.match(mensagem, /procure o administrador/);
  assert.doesNotMatch(mensagem, /Cliente privado/);
});
test('422 e 401 seguem o tratamento existente de validação e sessão', () => {
  const error = (status, detail) => new axios.AxiosError('erro', undefined, {}, undefined, { status, data: { detail } });
  assert.match(erroCliente(error(422, [{ msg: 'Nome não pode ser vazio' }]), 'Falha'), /Nome não pode ser vazio/);
  assert.match(erroCliente(error(401), 'Falha'), /Sessão expirada/);
});
test('consulta cadastral é somente leitura e trata email ausente', () => {
  const html = renderToStaticMarkup(createElement(DadosCadastraisCliente, { cliente: { id: 'a', nome: 'Ana', telefone: '123', email: null, ativo: true } }));
  assert.match(html, /Ana/); assert.match(html, /Não informado/); assert.match(html, /Ativo/);
  assert.doesNotMatch(html, /<input/);
});
