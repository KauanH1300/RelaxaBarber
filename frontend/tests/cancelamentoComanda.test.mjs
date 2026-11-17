import assert from 'node:assert/strict';
import test from 'node:test';
import { carregarTs } from './helpers/carregarTs.mjs';
const { default:api }=await carregarTs('services/api.ts');
const c=await carregarTs('services/cancelamentoComanda.ts');
const id='10000000-0000-4000-8000-000000000001';
const comanda={id,filial_id:id,status:'aberta',data_fechamento:null,itens:[],versao_itens:2};
const memory=new Map();globalThis.localStorage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};

test('perfis autorizados e ausência de itens ativos; total zero não é critério',()=>{
 for(const perfil of ['admin','recepcao'])assert.equal(c.podeCancelarComanda({perfil},comanda),true);
 for(const perfil of ['barbeiro','barbeiro_chefe'])assert.equal(c.podeCancelarComanda({perfil},comanda),false);
 for(const status of ['fechada','cancelada'])assert.equal(c.podeCancelarComanda({perfil:'admin'},{...comanda,status}),false);
 assert.equal(c.podeCancelarComanda({perfil:'admin'},{...comanda,itens:[{ativo:true,preco_unitario:'0.00'}]}),false);
 assert.equal(c.podeCancelarComanda({perfil:'recepcao'},{...comanda,itens:[{ativo:false}]}),true);
 assert.equal(c.podeCancelarComanda({perfil:'admin'},{...comanda,data_fechamento:'2026-01-01T12:00:00Z'}),false);
});

test('timeout conserva intenção original, chave e versão para replay',async()=>{
 const key=c.chaveCancelamento('admin',comanda),p={chave:id,payload:{versao:2,motivo:'Vazia conferida',confirmado:true}};
 memory.delete(key);c.salvarCancelamento(key,p);assert.throws(()=>c.salvarCancelamento(key,{...p,payload:{...p.payload,motivo:'Outro'}}));const calls=[];
 api.defaults.adapter=async config=>{calls.push({url:config.url,data:config.data,key:config.headers['Idempotency-Key'],filial:config.params.filial_id});if(calls.length===1)throw Error('timeout');return {data:{status:'cancelada'},status:200,statusText:'OK',headers:{},config};};
 await assert.rejects(()=>c.cancelarComanda(comanda,p));assert.deepEqual(c.lerCancelamento(key),p);
 assert.equal((await c.cancelarComanda(comanda,c.lerCancelamento(key))).status,'cancelada');assert.deepEqual(calls[0],calls[1]);
 assert.equal(calls[0].url,`/comandas/${id}/cancelamento`);assert.equal(calls[0].filial,id);
});

test('pendência inválida preservada para revisão',()=>{
 const key=c.chaveCancelamento('admin',comanda);
 for(const payload of [{versao:-1,motivo:'teste',confirmado:true},{versao:0,motivo:' ',confirmado:true},{versao:0,motivo:'teste',confirmado:false}]){
  const raw=JSON.stringify({chave:id,payload});memory.set(key,raw);assert.throws(()=>c.lerCancelamento(key));assert.equal(memory.get(key),raw);
 }
});
