import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement as h } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Routes, Route, Outlet } from 'react-router-dom';
import axios from 'axios';
import { carregarTs } from './helpers/carregarTs.mjs';

const storage = new Map();
globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
globalThis.window = new EventTarget();
const { default: api } = await carregarTs('services/api.ts');
api.defaults.adapter = () => { throw new Error('Rede proibida nos testes'); };
const { mensagemErro, escritaIncerta, deveConferirRegistros } = await carregarTs('services/erros.ts');
const { horariosAgenda, dataLocal } = await carregarTs('services/agenda.ts');
const { Perfil } = await carregarTs('pages/perfil/Perfil.tsx');
const { SomenteAdministrador } = await carregarTs('components/SomenteAdministrador.tsx');
const { Layout } = await carregarTs('components/layout.tsx');
const { Login } = await carregarTs('pages/auth/Login.tsx');

function error(status, detail, url='/agendamentos') {
  const config = { url, headers: new axios.AxiosHeaders() };
  return new axios.AxiosError('não apresentar dados internos', undefined, config, undefined,
    status ? { status, data: { detail }, headers: {}, config } : undefined);
}

for (const [detail, expected] of [
  ['Horário ocupado', 'Horário ocupado'],
  [['Preço inválido','Duração inválida'], 'Preço inválido; Duração inválida'],
  [[{ msg: 'Campo obrigatório', input: 'não exibir' }], 'Campo obrigatório'],
  [{ sql: 'SEGREDO' }, 'Falha segura'],
]) {
  test(`mensagem segura: ${JSON.stringify(detail)}`, () => assert.equal(mensagemErro(error(422, detail), 'Falha segura'), expected));
}
test('conflitos e falhas de confirmação exigem consulta, sem supor rollback', () => {
  for (const status of [500,502,503,504,undefined]) {
    assert.equal(escritaIncerta(error(status)), true);
    assert.equal(deveConferirRegistros(error(status)), true);
  }
  assert.equal(escritaIncerta(error(409)), false);
  assert.equal(deveConferirRegistros(error(409)), true);
  for (const status of [400,401,403,422]) assert.equal(deveConferirRegistros(error(status)), false);
  assert.equal(mensagemErro(error(401), 'Falha'), 'Sessão expirada. Entre novamente.');
  assert.equal(mensagemErro(error(401,'E-mail ou senha inválidos','/auth/login'), 'Falha'), 'E-mail ou senha inválidos');
});

test('grade cobre todos os horários retornados, incluindo extremos, sem duplicar blocos', () => {
  const starts=['00:01','07:30','07:45','08:15','18:30','19:00','23:59'];
  const grade=horariosAgenda(starts);
  assert.equal(new Set(grade).size,grade.length);
  for (const inicio of starts) {
    const [hour,minute]=inicio.split(':').map(Number);const total=hour*60+minute;
    assert.equal(grade.filter((block) => {
      const [h,m]=block.split(':').map(Number);return total>=h*60+m && total<h*60+m+30;
    }).length,1);
  }
  assert.equal(grade[0],'00:00');assert.equal(grade.at(-1),'23:30');
  assert.equal(dataLocal(new Date(2030,11,31)), '2030-12-31');
});

function renderUser(component, perfil='barbeiro') {
  const usuario={id:'ficticio',nome:'Usuário de teste',email:'teste@example.com',telefone:null,perfil,ativo:true,data_cadastro:'2030-01-01T12:00:00Z'};
  return renderToStaticMarkup(h(MemoryRouter,null,h(Routes,null,h(Route,{element:h(Outlet,{context:{usuario}})},h(Route,{path:'/',element:component})))));
}
test('perfil só leitura exibe dados e não oferece formulário ou senha', () => {
  const html=renderUser(h(Perfil));
  for (const value of ['Usuário de teste','teste@example.com','Não informado','Barbeiro']) assert.ok(html.includes(value));
  assert.doesNotMatch(html,/<(input|form)|senha_hash/i);
});
for (const perfil of ['admin','recepcao','barbeiro','barbeiro_chefe']) {
  test(`formulário administrativo protegido para ${perfil}`, () => {
    const html=renderUser(h(SomenteAdministrador,null,h('form',null,'conteúdo restrito')),perfil);
    assert.equal(html.includes('conteúdo restrito'),perfil==='admin');
    assert.equal(html.includes('Sem permissão'),perfil!=='admin');
  });
}
test('shell não monta páginas internas enquanto valida sessão', () => {
  storage.set('token','token-ficticio');
  const html=renderToStaticMarkup(h(MemoryRouter,null,h(Layout)));
  assert.ok(html.includes('Validando sessão'));assert.doesNotMatch(html,/Agendamentos|Meu perfil/);
  storage.clear();
});
test('login é por e-mail e senha e não anuncia Google ou recuperação simulada', () => {
  const html=renderToStaticMarkup(h(MemoryRouter,null,h(Login)));
  assert.match(html,/type="email"/);assert.doesNotMatch(html,/Google|E-mail ou Telefone/);
  assert.ok(html.includes('Recuperação de senha indisponível'));
});

for (const status of [401,403,503,undefined]) {
  test(`interceptor: status ${status} não repete requisição e só 401 encerra sessão`, async () => {
    storage.set('token','token-ficticio');let calls=0;
    api.defaults.adapter = async (config) => { calls++;throw new axios.AxiosError('simulado',undefined,config,undefined,
      status ? {status,data:{detail:'falha simulada'},config,headers:{}} : undefined); };
    await assert.rejects(api.get('/auth/me'));
    assert.equal(calls,1);assert.equal(storage.has('token'),status!==401);
    storage.clear();
  });
}
test('401 de uma requisição antiga não remove um token novo', async () => {
  storage.set('token','antigo');
  api.defaults.adapter = async (config) => {
    storage.set('token','novo');
    throw new axios.AxiosError('simulado',undefined,config,undefined,{status:401,data:{},config,headers:{}});
  };
  await assert.rejects(api.get('/auth/me'));
  assert.equal(storage.get('token'),'novo');storage.clear();
});
test('credenciais inválidas no login não disparam expiração global', async () => {
  storage.set('token','existente');
  api.defaults.adapter = async (config) => { throw new axios.AxiosError('simulado',undefined,config,undefined,{status:401,data:{},config,headers:{}}); };
  await assert.rejects(api.post('/auth/login',{}));
  assert.equal(storage.get('token'),'existente');storage.clear();
});
