/** Firefox e API simulada estritamente local; sem rede externa ou Supabase. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),profile=await mkdtemp(join(tmpdir(),'rb-beneficios-'));
const id='10000000-0000-4000-8000-000000000001',unit='20000000-0000-4000-8000-000000000001',item='30000000-0000-4000-8000-000000000001',user='40000000-0000-4000-8000-000000000001';
let role='admin',total='30.00',itemTotal='30.00',received='0.00',version=0,closed=false,type='nenhum',value='0.00',generalType='nenhum',generalValue='0.00',history=[],empty=false,lastPreview;
const requests=[];
const initialItem=()=>({id:item,tipo:'servico',servico_id:id,descricao:'Serviço fictício',quantidade:3,preco_unitario:'10.00',subtotal_bruto:'30.00',desconto_tipo:type,desconto_valor:value,desconto_aplicado:String((30-Number(itemTotal)).toFixed(2)),subtotal:itemTotal,ativo:true});
const state=()=>({itens:empty?[]:[initialItem()],desconto_tipo:generalType,desconto_valor:generalValue,total_bruto:empty?'0.00':'30.00',desconto_itens:empty?'0.00':String((30-Number(itemTotal)).toFixed(2)),subtotal:itemTotal,desconto_geral:(Number(itemTotal)-Number(total)).toFixed(2),total});
const detail=()=>({id,filial_id:unit,agendamento_id:id,cliente_id:id,barbeiro_id:user,status:closed?'fechada':'aberta',versao_itens:version,desconto_tipo:generalType,desconto_valor:generalValue,data_abertura:'2026-11-17T10:00:00Z',data_fechamento:closed?'2026-11-17T12:00:00Z':null,itens:state().itens,total,status_apresentacao:closed?'fechada':total===received?'aguardando_fechamento':'aberta',cliente:{id,nome:'Cliente fictício'},profissional:{id:user,nome:'Profissional fictício'},filial:{id:unit,nome:'Unidade fictícia'},atendimento:{id,data:new Intl.DateTimeFormat('en-CA',{timeZone:'America/Recife'}).format(new Date()),hora_inicio:'10:00:00',hora_fim:'10:30:00',status:'em_atendimento'},descontos:state()});
const server=createServer(async(req,res)=>{
 res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type, Idempotency-Key');
 if(req.method==='OPTIONS')return res.writeHead(204).end();
 const url=new URL(req.url,'http://localhost');let raw='';for await(const chunk of req)raw+=chunk;const body=raw?JSON.parse(raw):null;
 requests.push({method:req.method,path:url.pathname,body,key:req.headers['idempotency-key']});
 const reply=(code,data)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
 if(url.pathname==='/auth/me')return reply(200,{id:user,nome:'Operador fictício',email:'fixture@example.com',perfil:role,ativo:true});
 if(url.pathname==='/filiais')return reply(200,[{id:unit,nome:'Unidade fictícia',fuso_horario:'America/Recife'}]);
 if(url.pathname==='/usuarios/barbeiros')return reply(200,[{id:user,nome:'Profissional fictício'}]);
 if(url.pathname==='/comandas/painel')return reply(200,{itens:[detail()],total:1,pagina:1,tamanho:6,indicadores:{contagens:{aberta:closed?0:1,fechada:closed?1:0,pendente:0,cancelada:0},valor_abertas:closed?'0.00':total,pagamentos_disponiveis:true}});
 if(url.pathname===`/comandas/${id}`)return reply(200,detail());
 if(url.pathname.endsWith('/financeiro'))return reply(200,{comanda_id:id,filial_id:unit,situacao:closed?'fechado':'aberto',total,recebido_liquido:received,pagamentos:received,estornos:'0.00',saldo:(Number(total)-Number(received)).toFixed(2),historico:{pagamentos:[],estornos:[]}});
 if(url.pathname.endsWith('/itens/alteracoes'))return reply(200,[]);
 if(url.pathname.endsWith('/beneficios')&&req.method==='GET')return reply(200,history);
 if(url.pathname.endsWith('/beneficios/previa')){
  const anterior=state(),gratis=body.acao==='encerramento_gratuito';
  const general=body.acao==='comanda';
  const newTotal=gratis?total:general?(body.desconto_tipo==='valor'?'20.00':'24.30'):body.desconto_tipo==='cortesia'?'0.00':body.desconto_tipo==='percentual'?'27.00':'10.00';
  const posterior=general?{...anterior,total:newTotal,desconto_tipo:body.desconto_tipo,desconto_valor:body.desconto_valor,desconto_geral:(Number(itemTotal)-Number(newTotal)).toFixed(2)}:{...anterior,total:newTotal,subtotal:newTotal,desconto_itens:(30-Number(newTotal)).toFixed(2),itens:anterior.itens.map(i=>({...i,desconto_tipo:body.desconto_tipo??type,desconto_valor:body.desconto_valor??value,subtotal:newTotal,desconto_aplicado:(30-Number(newTotal)).toFixed(2)}))};
  lastPreview={comanda_id:id,versao:version,anterior,posterior,recebido_liquido:received,saldo:(Number(newTotal)-Number(received)).toFixed(2),exige_fechamento:Number(received)>0&&newTotal===received,exige_gratuidade:gratis,conferencia:'a'.repeat(64)};
  return reply(200,lastPreview);
 }
 if(url.pathname.endsWith('/beneficios')&&req.method==='POST'){
  assert.ok(['admin','recepcao'].includes(role));assert.equal(body.versao,version);assert.equal(body.conferencia,'a'.repeat(64));
  if(lastPreview.exige_fechamento)assert.equal(body.confirmar_fechamento,true);
  if(lastPreview.exige_gratuidade)assert.equal(body.confirmar_gratuidade,true);
  total=lastPreview.posterior.total;itemTotal=lastPreview.posterior.subtotal;closed=lastPreview.exige_fechamento||lastPreview.exige_gratuidade;
  if(body.acao==='comanda'){generalType=body.desconto_tipo;generalValue=body.desconto_valor;}else{type=body.desconto_tipo??type;value=body.desconto_valor??value;}version++;
  const result={...lastPreview,versao:version,acao:body.acao,item_id:body.item_id??null,motivo:body.motivo,registrado_por:user,registrado_em:'2026-11-17T12:00:00Z',chave_idempotencia:req.headers['idempotency-key'],fechado:closed};history.push(result);return reply(200,result);
 }
 return reply(404,{});
});
let vite,firefox,ws;
async function wait(check,label){const end=Date.now()+15000;while(Date.now()<end){try{if(await check())return;}catch{}await new Promise(resolve=>setTimeout(resolve,100));}throw Error('Tempo excedido: '+label);}
try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const api=server.address().port;
 vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5179','--strictPort'],{cwd:root,env:{...process.env,VITE_API_URL:`http://127.0.0.1:${api}`},stdio:'ignore'});
 await wait(async()=>(await fetch('http://127.0.0.1:5179')).ok,'Vite');
 firefox=spawn(process.env.FIREFOX_BIN||'/usr/bin/firefox',['--headless','--no-remote','--profile',profile,'--remote-debugging-port','9239'],{stdio:'ignore',env:{...process.env,MOZ_DISABLE_CONTENT_SANDBOX:'1'}});
 await wait(async()=>{await fetch('http://127.0.0.1:9239/');return true;},'Firefox');
 ws=new WebSocket('ws://127.0.0.1:9239/session');await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 let sequence=0;const pending=new Map();ws.addEventListener('message',({data})=>{const b=JSON.parse(data),p=pending.get(b.id);if(p){clearTimeout(p.timer);pending.delete(b.id);b.type==='error'?p.reject(Error(b.message)):p.resolve(b.result);}});
 const cmd=(method,params={})=>new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(Error(method)),20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
 await cmd('session.new',{capabilities:{alwaysMatch:{}}});const {context}=await cmd('browsingContext.create',{type:'tab'});
 const ev=async expression=>{const r=await cmd('script.evaluate',{expression,target:{context},awaitPromise:true});if(r.type==='exception')throw Error(r.exceptionDetails.text);return r.result.value;};
 const section='.comanda-beneficios';
 const button=async text=>{await wait(()=>ev(`[...document.querySelectorAll('${section} button')].some(b=>b.textContent===${JSON.stringify(text)}&&!b.disabled)`),text);await ev(`[...document.querySelectorAll('${section} button')].find(b=>b.textContent===${JSON.stringify(text)}).click()`);};
 const set=(selector,value)=>ev(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e),'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`);
 async function open(){
  await cmd('browsingContext.navigate',{context,url:'http://127.0.0.1:5179/login',wait:'complete'});await ev(`localStorage.setItem('token','fixture');localStorage.setItem('relaxabarber:filial:${user}','${unit}')`);
  await cmd('browsingContext.navigate',{context,url:'http://127.0.0.1:5179/comandas',wait:'complete'});
  await wait(()=>ev(`!!document.querySelector('.comanda-card footer button')`),'Card');await ev(`document.querySelector('.comanda-card footer button').click()`);
  await wait(()=>ev(`!!document.querySelector('${section}')`),'Beneficios');
 }
 async function preview(tipo,valor){
  await button('Conceder ou alterar benefício');await set(`${section} select`,item);await set(`${section} label:nth-child(3) select`,tipo);
  if(valor!==null)await set(`${section} input[type=number]`,valor);
  await set(`${section} textarea`,'Benefício fictício autorizado');await button('Consultar prévia do benefício');
  await wait(()=>ev(`!!document.querySelector('${section} [aria-label="Revisão do benefício"]')`),'Previa');
 }
 await open();await preview('percentual','10');assert.equal(version,0);assert.ok(await ev(`document.querySelector('${section}').textContent.includes('27,00')`));
 await button('Cancelar benefício');assert.equal(version,0);
 await preview('percentual','10');await button('Confirmar benefício');await wait(()=>version===1,'Confirmacao');
 await wait(()=>ev(`document.querySelectorAll('${section} details li').length===1`),'Historico');assert.equal(total,'27.00');
 console.log('PASS Firefox: percentual, previa/cancelamento, confirmacao e historico');
 for(const [tipo,valor,expected] of [['valor','7','20.00'],['percentual','10','24.30']]){
  const count=history.length;await button('Conceder ou alterar benefício');await set(`${section} label:nth-child(3) select`,tipo);await set(`${section} input[type=number]`,valor);await set(`${section} textarea`,'Desconto geral fictício');await button('Consultar prévia do benefício');
  await wait(()=>ev(`!!document.querySelector('${section} [aria-label="Revisão do benefício"]')`),'Desconto geral');await button('Confirmar benefício');await wait(()=>history.length===count+1,'Aplicar geral');assert.equal(total,expected);
  await wait(()=>ev(`document.querySelectorAll('${section} details li').length===${count+1}`),'Historico geral');assert.equal(requests.filter(r=>r.method==='POST'&&r.path.endsWith('/beneficios')).at(-1).body.acao,'comanda');
 }
 console.log('PASS Firefox: descontos gerais em R$ e percentual apos beneficio individual');
 total=itemTotal='30.00';received='10.00';version=0;history=[];type='nenhum';value='0.00';generalType='nenhum';generalValue='0.00';await open();
 await preview('valor','20');assert.ok(await ev(`[...document.querySelectorAll('${section} button')].find(b=>b.textContent==='Confirmar benefício e encerramento').disabled`));
 await button('Cancelar benefício');assert.equal(version,0);assert.equal(closed,false);
 await preview('valor','20');await ev(`document.querySelector('${section} input[type=checkbox]').click()`);await button('Confirmar benefício e encerramento');await wait(()=>closed,'OPCAO B');assert.equal(received,'10.00');assert.equal(history.length,1);
 console.log('PASS Firefox: OPCAO B exige confirmacao; cancelar nao persiste; confirmar encerra sem pagamento');
 total=itemTotal='30.00';received='0.00';version=0;closed=false;history=[];type='nenhum';value='0.00';await open();await preview('cortesia',null);await button('Confirmar benefício');await wait(()=>version===1,'Cortesia');assert.equal(closed,false);assert.equal(total,'0.00');
 await button('Encerrar comanda gratuita');await set(`${section} textarea`,'Encerramento gratuito fictício');await button('Consultar prévia do benefício');
 await wait(()=>ev(`!!document.querySelector('${section} input[type=checkbox]')`),'Confirmacao gratuidade');
 assert.ok(await ev(`[...document.querySelectorAll('${section} button')].find(b=>b.textContent==='Confirmar benefício e encerramento').disabled`));
 await ev(`document.querySelector('${section} input[type=checkbox]').click()`);await button('Confirmar benefício e encerramento');await wait(()=>closed,'Encerramento gratuito');assert.equal(history.length,2);assert.equal(received,'0.00');
 console.log('PASS Firefox: cortesia preserva preco; zero permanece aberto ate encerramento explicito');
 for(const perfil of ['barbeiro','barbeiro_chefe']){role=perfil;closed=false;total='30.00';await open();assert.equal(await ev(`document.querySelectorAll('${section} button').length`),0);}
 role='admin';empty=true;total='0.00';await open();assert.equal(await ev(`[...document.querySelectorAll('${section} button')].filter(b=>b.textContent==='Encerrar comanda gratuita').length`),0);
 assert.ok(requests.filter(r=>r.method==='POST').every(r=>r.path.includes('/beneficios')));
 console.log('PASS Firefox: perfis sem concessao e comanda vazia sem encerramento');
 if(process.env.BENEFICIOS_SCREENSHOT_DIR){const x=await cmd('browsingContext.captureScreenshot',{context});await writeFile(join(process.env.BENEFICIOS_SCREENSHOT_DIR,'beneficios-firefox.png'),Buffer.from(x.data,'base64'));}
 await cmd('session.end');
}finally{if(ws)ws.close();if(firefox)firefox.kill();if(vite)vite.kill();server.close();await rm(profile,{recursive:true,force:true});}
