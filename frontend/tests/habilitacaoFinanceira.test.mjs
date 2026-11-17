import test from 'node:test';
import assert from 'node:assert/strict';
import axios from 'axios';
import { carregarTs } from './helpers/carregarTs.mjs';
const memoria=new Map();
globalThis.sessionStorage={getItem:k=>memoria.get(k)??null,setItem:(k,v)=>memoria.set(k,v),removeItem:k=>memoria.delete(k)};
globalThis.localStorage={getItem:()=> 'token-ficticio'};
globalThis.window=new EventTarget();
const f=await carregarTs('services/financeiro.ts');
const {default:api}=await carregarTs('services/api.ts');
const filial=await carregarTs('services/filialAtiva.ts');
const comanda={id:'comanda',filial_id:'filial'};
const pendente={chave:'11111111-1111-4111-8111-111111111111',operacao:'habilitacao-financeira',payload:{conferencia:'a'.repeat(64),confirmado:true,motivo:'Conferido'}};

test('habilitacao incerta preserva chave e payload sem criar recebimentos',async()=>{
  filial.mudarContexto('token-ficticio','filial');
  const storage=f.chaveStorage('recepcao',comanda),calls=[];
  let confirmacoes=0;
  const registros=new Set();
  api.defaults.adapter=async config=>{
    calls.push({url:config.url,payload:config.data,key:config.headers.get('Idempotency-Key'),filial:config.params.filial_id});
    if(!registros.has(calls.at(-1).key)){registros.add(calls.at(-1).key);confirmacoes++;}
    if(calls.length===1)throw new axios.AxiosError('timeout ficticio','ECONNABORTED',config);
    return {status:200,data:{registrado_por:'recepcao'},config};
  };
  f.salvarPendente(storage,pendente);
  await assert.rejects(f.enviarFinanceiro(comanda,pendente),e=>f.resultadoIncerto(e));
  assert.deepEqual(f.lerPendente(storage),pendente);
  assert.throws(()=>f.salvarPendente(storage,{...pendente,chave:'22222222-2222-4222-8222-222222222222'}));
  await f.recuperarFinanceiro(comanda,storage);
  assert.deepEqual(calls[0],calls[1]);assert.equal(confirmacoes,1);
  assert.ok(calls.every(c=>c.url.endsWith('/habilitacao-financeira')&&c.filial==='filial'));
  assert.ok(!calls[0].payload.includes('pagamentos'));
  await assert.rejects(f.recuperarFinanceiro({...comanda,filial_id:'outra'},storage));
  f.limparPendente(storage,pendente);
  assert.equal(f.lerPendente(storage),null);
});

test('exige conferencia valida, confirmacao explicita e motivo sem campos extras',()=>{
  const key=f.chaveStorage('admin',comanda);
  for(const mudanca of [{conferencia:'invalida'},{confirmado:false},{motivo:' '},{cliente_id:'outro'},{motivo:'x'.repeat(1001)}]){
    assert.throws(()=>f.salvarPendente(key,{...pendente,payload:{...pendente.payload,...mudanca}}));
    assert.equal(f.lerPendente(key),null);
  }
});
