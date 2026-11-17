import assert from 'node:assert/strict';
import test from 'node:test';
import { carregarTs } from './helpers/carregarTs.mjs';
const f=await carregarTs('services/financeiro.ts');
const {default:api}=await carregarTs('services/api.ts');
const memoria=new Map();
globalThis.sessionStorage={getItem:k=>memoria.get(k)??null,setItem:(k,v)=>memoria.set(k,v),removeItem:k=>memoria.delete(k)};
globalThis.localStorage={getItem:()=>null};
const resumo={situacao:'aberto',saldo:'20.50',total:'30.50',recebido_liquido:'10.00'};
const data=new Date(Date.now()-60000).toISOString();
const p={valor:'10,00',forma:'pix',confirmado:true};
test('parcial aceita, integral aceita, excesso e promessa recusados',()=>{
 assert.equal(f.prepararRecebimentos(resumo,[p],data,false).pagamentos[0].valor,'10.00');
 assert.equal(f.prepararRecebimentos(resumo,[{...p,valor:'20,50'}],data,false).pagamentos[0].valor,'20.50');
 for(const changes of [{valor:'20.51'},{valor:'0'},{confirmado:false},{forma:'qr_code'}])assert.throws(()=>f.prepararRecebimentos(resumo,[{...p,...changes}],data,false));
 assert.throws(()=>f.prepararRecebimentos({...resumo,saldo:'0.00'},[p],data,false));
 assert.throws(()=>f.prepararRecebimentos(resumo,[],data,false));
});
test('independencia operacional e bloqueios financeiros',()=>{
 for(const status of ['em_atendimento','concluido'])assert.equal(f.podeMovimentar({status:'aberta',atendimento:{status}},resumo),true);
 for(const status of ['pendente','aguardando'])assert.equal(f.podeMovimentar({status:'aberta',atendimento:{status}},resumo),false);
 assert.equal(f.podeMovimentar({status:'aberta',atendimento:{status:'cancelado'}},resumo),false);
 for(const situacao of ['fechado','nao_verificado'])assert.equal(f.podeMovimentar({status:'aberta',atendimento:{status:'em_atendimento'}},{...resumo,situacao}),false);
});
test('replay conserva chave e payload apos timeout e consulta posterior',async()=>{
 const c={id:'fixture',filial_id:'filial'};const storage=f.chaveStorage('user',c);
 const pending={operacao:'recebimentos',chave:'11111111-1111-4111-8111-111111111111',payload:f.prepararRecebimentos(resumo,[p],data,false)};
 const sent=[];
 api.defaults.adapter=async config=>{sent.push({url:config.url,data:config.data,key:config.headers['Idempotency-Key']});if(sent.length===1)throw Error('timeout ficticio');return {data:[{id:'receipt'}],status:200,statusText:'OK',headers:{},config};};
 f.salvarPendente(storage,pending);
 await assert.rejects(()=>f.enviarFinanceiro(c,pending));
 assert.deepEqual(f.lerPendente(storage),pending);
 assert.throws(()=>f.salvarPendente(storage,{...pending,chave:'22222222-2222-4222-8222-222222222222'}));
 await f.recuperarFinanceiro(c,storage);
 assert.deepEqual(sent[0],sent[1]);assert.ok(sent[0].url.endsWith('/recebimentos'));
 f.limparPendente(storage,pending);assert.equal(f.lerPendente(storage),null);
});
