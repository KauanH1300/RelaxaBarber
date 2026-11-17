import assert from 'node:assert/strict';
import test from 'node:test';
import { carregarTs } from './helpers/carregarTs.mjs';
const b=await carregarTs('services/beneficios.ts');
const {default:api}=await carregarTs('services/api.ts');
const memory=new Map();
globalThis.sessionStorage={getItem:k=>memory.get(k)??null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
globalThis.localStorage={getItem:()=>null};
const id='11111111-1111-4111-8111-111111111111';
const c={id,filial_id:id,barbeiro_id:'prof',status:'aberta',status_apresentacao:'aberta',versao_itens:2,atendimento:{status:'em_atendimento'}};
const payload={acao:'item',item_id:id,desconto_tipo:'percentual',desconto_valor:'20.00',versao:2,motivo:'Conferido',conferencia:'a'.repeat(64),confirmar_fechamento:true,confirmar_gratuidade:false};
test('beneficios somente para admin/recepcao em comanda elegivel',()=>{
 for(const perfil of ['admin','recepcao'])assert.equal(b.podeBeneficiar({id:'prof',perfil},c),true);
 for(const perfil of ['barbeiro','barbeiro_chefe'])assert.equal(b.podeBeneficiar({id:'prof',perfil},c),false);
 for(const status_apresentacao of ['fechada','nao_verificado','restrito'])assert.equal(b.podeBeneficiar({id:'prof',perfil:'admin'},{...c,status_apresentacao}),false);
});
test('previa nao grava pendencia e conserva versao/contexto',async()=>{
 let cfg;api.defaults.adapter=async config=>{cfg=config;return {data:{exige_gratuidade:true},status:200,statusText:'OK',headers:{},config};};
 assert.equal((await b.previaBeneficio(c,{acao:'encerramento_gratuito',versao:2,motivo:'Conferido'})).exige_gratuidade,true);
 assert.equal(cfg.url,`/comandas/${id}/beneficios/previa`);assert.equal(cfg.params.filial_id,id);assert.equal(memory.size,0);
});
test('resposta perdida preserva chave, conteudo e confirmacoes no replay',async()=>{
 const key=b.chaveBeneficio('admin',c),p={chave:id,payload};const calls=[];
 api.defaults.adapter=async config=>{calls.push({url:config.url,data:config.data,key:config.headers['Idempotency-Key']});if(calls.length===1)throw Error('timeout');return {data:{fechado:true},status:200,statusText:'OK',headers:{},config};};
 b.salvarBeneficio(key,p);await assert.rejects(()=>b.aplicarBeneficio(c,p));assert.deepEqual(b.lerBeneficio(key),p);
 assert.throws(()=>b.salvarBeneficio(key,{...p,payload:{...payload,motivo:'Outro'}}));
 await b.aplicarBeneficio(c,b.lerBeneficio(key));assert.deepEqual(calls[0],calls[1]);b.limparBeneficio(key,p);assert.equal(b.lerBeneficio(key),null);
});
test('conteudo invalido nao e enviado nem apagado',()=>{
 const key=b.chaveBeneficio('admin',c);
 for(const change of [{desconto_valor:'-1'},{desconto_valor:'101'},{desconto_valor:'0.001'},{confirmar_gratuidade:'true'},{preco_unitario:'0'},{versao:-1},{acao:'comanda'},{desconto_tipo:'cortesia',desconto_valor:'1'}]){
  const raw=JSON.stringify({chave:id,payload:{...payload,...change}});memory.set(key,raw);assert.throws(()=>b.lerBeneficio(key));assert.equal(memory.get(key),raw);
 }
 memory.clear();
});
test('encerramento gratuito preserva confirmacao explicita sem pagamento',async()=>{
 const key=b.chaveBeneficio('admin',c),p={chave:id,payload:{acao:'encerramento_gratuito',versao:2,motivo:'Cortesia autorizada',conferencia:'b'.repeat(64),confirmar_fechamento:false,confirmar_gratuidade:true}};
 b.salvarBeneficio(key,p);assert.deepEqual(b.lerBeneficio(key),p);b.limparBeneficio(key,p);
});
