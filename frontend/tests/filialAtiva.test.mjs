import assert from 'node:assert/strict';
import test from 'node:test';
import axios from 'axios';
import { carregarTs } from './helpers/carregarTs.mjs';

const storage = new Map();
globalThis.localStorage = { getItem: (k) => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v), removeItem: (k) => storage.delete(k) };
globalThis.window = new EventTarget();
const contexto = await carregarTs('services/filialAtiva.ts');
const { default: api } = await carregarTs('services/api.ts');
const a = { id: 'a', nome: 'A', fuso_horario: 'America/Recife' };
const b = { ...a, id: 'b', nome: 'B' };

test('restauração exige acesso atual e preferência é isolada por usuário', () => {
  assert.equal(contexto.filialRestauravel([a], null), 'a');
  assert.equal(contexto.filialRestauravel([a,b], null), null);
  assert.equal(contexto.filialRestauravel([a,b], 'revogada'), null);
  assert.equal(contexto.filialRestauravel([a,b], 'b'), 'b');
  assert.equal(contexto.filialRestauravel([], 'b'), null);
  contexto.salvarPreferencia('um', 'a');contexto.salvarPreferencia('dois', 'b');
  assert.equal(contexto.lerPreferencia('um'), 'a');assert.equal(contexto.lerPreferencia('dois'), 'b');
});

for (const path of ['/agendamentos','/usuarios/barbeiros','/clientes','/clientes/pesquisa','/clientes/uuid/resumo','/clientes/uuid/resumo-financeiro','/comandas']) {
  test(`requisição usa filial atual: ${path}`, async () => {
    storage.set('token','jwt');contexto.mudarContexto('jwt','a');
    api.defaults.adapter = async (config) => {
      assert.equal(config.params.filial_id,'a');
      return {status:200,data:[],headers:{},config};
    };
    await api.get(path);
  });
}

test('POST envia unidade explícita e impede formulário com contexto antigo', async () => {
  storage.set('token','jwt');contexto.mudarContexto('jwt','b');let calls=0;
  api.defaults.adapter = async (config) => {
    calls++;assert.equal(JSON.parse(config.data).filial_id,'b');return {status:201,data:{},headers:{},config};
  };
  await api.post('/agendamentos',{cliente_id:'ficticio'});
  await assert.rejects(api.post('/agendamentos',{filial_id:'a'}),axios.isCancel);
  assert.equal(calls,1);
});

for (const resource of ['/agendamentos','/usuarios/barbeiros','/clientes','/clientes/uuid/resumo','/clientes/uuid/resumo-financeiro','/comandas']) {
  test(`resposta atrasada não é consumida após troca, inclusive A-B-A: ${resource}`, async () => {
    storage.set('token','jwt');contexto.mudarContexto('jwt','a');let release;let ready;
    const started=new Promise((resolve) => { ready=resolve; });
    api.defaults.adapter = (config) => new Promise((resolve) => {
      release=() => resolve({status:200,data:['dados antigos'],headers:{},config});ready();
    });
    const pending=api.get(resource);await started;
    contexto.mudarContexto('jwt','b');contexto.mudarContexto('jwt','a');release();
    await assert.rejects(pending,axios.isCancel);
  });
}

test('403 revalida acesso sem deslogar e resposta antiga não invalida contexto novo', async () => {
  storage.set('token','jwt');contexto.mudarContexto('jwt','a');let events=0;
  const handler=() => { events++; };window.addEventListener(contexto.EVENTO_ACESSO_FILIAIS,handler);
  api.defaults.adapter=async (config) => { throw new axios.AxiosError('negado',undefined,config,undefined,{status:403,data:{},headers:{},config}); };
  await assert.rejects(api.get('/clientes'));assert.equal(events,1);assert.equal(storage.get('token'),'jwt');
  api.defaults.adapter=async (config) => {
    contexto.mudarContexto('jwt','b');throw new axios.AxiosError('antigo',undefined,config,undefined,{status:403,data:{},headers:{},config});
  };
  await assert.rejects(api.get('/clientes'),axios.isCancel);assert.equal(events,1);
  window.removeEventListener(contexto.EVENTO_ACESSO_FILIAIS,handler);
});

test('operação iniciada com filial antiga não é reenviada na unidade atual', async () => {
  storage.set('token','jwt');contexto.mudarContexto('jwt','b');let calls=0;
  api.defaults.adapter=async (config) => { calls++;return {status:200,data:{},headers:{},config}; };
  await assert.rejects(api.patch('/agendamentos/uuid/status',{status:'cancelado'},{params:{filial_id:'a'}}),axios.isCancel);
  assert.equal(calls,0);
});
