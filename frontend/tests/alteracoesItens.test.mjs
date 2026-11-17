import assert from 'node:assert/strict';
import test from 'node:test';
import { carregarTs } from './helpers/carregarTs.mjs';
const a=await carregarTs('services/alteracoesItens.ts');
const {default:api}=await carregarTs('services/api.ts');
const memoria=new Map();
globalThis.sessionStorage={getItem:k=>memoria.get(k)??null,setItem:(k,v)=>memoria.set(k,v),removeItem:k=>memoria.delete(k)};
globalThis.localStorage={getItem:()=>null};
const id='11111111-1111-4111-8111-111111111111';
const c={id,filial_id:'22222222-2222-4222-8222-222222222222',barbeiro_id:'prof',status:'aberta',status_apresentacao:'aberta',versao_itens:2,atendimento:{status:'em_atendimento'}};
const payload={acao:'quantidade',quantidade:1,versao:2,motivo:'Conferido',conferencia:'a'.repeat(64),confirmar_fechamento:true};
test('gestores autorizados; barbeiros, fechamento e não verificado sem ajuste',()=>{
 for(const perfil of ['admin','recepcao'])assert.equal(a.podeAjustar({id:'prof',perfil},c),true);
 for(const perfil of ['barbeiro','barbeiro_chefe'])assert.equal(a.podeAjustar({id:'prof',perfil},c),false);
 for(const status_apresentacao of ['fechada','nao_verificado'])assert.equal(a.podeAjustar({id:'prof',perfil:'admin'},{...c,status_apresentacao}),false);
});
test('prévia não aplica ajuste nem persiste pendência',async()=>{
 let config;
 api.defaults.adapter=async cfg=>{config=cfg;return {data:{total:'10.00',saldo:'0.00',exige_fechamento:true},status:200,statusText:'OK',headers:{},config:cfg};};
 const p=await a.previaAjuste(c,id,{acao:'quantidade',quantidade:1,versao:2,motivo:'Conferido'});
 assert.equal(p.exige_fechamento,true);assert.ok(config.url.endsWith('/previa'));assert.equal(memoria.size,0);
});
test('timeout conserva chave, versão, conferência e confirmação da OPÇÃO B',async()=>{
 const storage=a.chaveAjuste('admin',c),pending={itemId:id,chave:id,payload};
 const sent=[];
 api.defaults.adapter=async cfg=>{sent.push({url:cfg.url,data:cfg.data,key:cfg.headers['Idempotency-Key']});if(sent.length===1)throw Error('timeout ficticio');return {data:{fechado:true},status:200,statusText:'OK',headers:{},config:cfg};};
 a.salvarAjuste(storage,pending);await assert.rejects(()=>a.aplicarAjuste(c,pending));assert.deepEqual(a.lerAjuste(storage),pending);
 assert.throws(()=>a.salvarAjuste(storage,{...pending,payload:{...payload,quantidade:2}}));
 await a.aplicarAjuste(c,a.lerAjuste(storage));assert.deepEqual(sent[0],sent[1]);
 a.limparAjuste(storage,pending);assert.equal(a.lerAjuste(storage),null);
});
test('registro inválido não é apagado nem enviado',()=>{
 const storage=a.chaveAjuste('admin',c);
 for(const mudanca of [{confirmar_fechamento:'true'},{quantidade:0},{acao:'desconto'},{servico_id:id},{versao:-1},{preco_unitario:'1.00'}]){
  const raw=JSON.stringify({itemId:id,chave:id,payload:{...payload,...mudanca}});memoria.set(storage,raw);
  assert.throws(()=>a.lerAjuste(storage));assert.equal(memoria.get(storage),raw);
 }
 memoria.clear();
});
