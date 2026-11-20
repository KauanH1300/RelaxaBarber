/** UI real no Firefox com API simulada local, sem acesso ao Supabase. */
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),profile=await mkdtemp(join(tmpdir(),'rb-cancelamento-'));
const id='10000000-0000-4000-8000-000000000001',unit='20000000-0000-4000-8000-000000000001',user='40000000-0000-4000-8000-000000000001';
let role='admin',closed=false,version=0,cancellation=null,loseResponse=false,rejeitar=false;
const posts=[];
let chaveRepasse, mostrarRepasse=false, falharConsulta=false, repassesEnviados=0;
const detail=()=>({id,filial_id:unit,agendamento_id:id,cliente_id:id,barbeiro_id:user,status:closed?'cancelada':'aberta',versao_itens:version,data_abertura:'2026-11-17T10:00:00Z',data_fechamento:null,itens:[],total:'0.00',status_apresentacao:closed?'cancelada':'aberta',cliente:{id,nome:'Cliente fictício'},profissional:{id:user,nome:'Profissional fictício'},filial:{id:unit,nome:'Unidade fictícia'},atendimento:{id,data:'2026-11-17',hora_inicio:'10:00:00',hora_fim:'10:30:00',status:'aguardando'},cancelamento:cancellation});
const server=createServer(async(req,res)=>{
 res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type, Idempotency-Key');
 if(req.method==='OPTIONS')return res.writeHead(204).end();
 const url=new URL(req.url,'http://localhost');let raw='';for await(const chunk of req)raw+=chunk;const body=raw?JSON.parse(raw):null;
 const reply=(code,data)=>{res.writeHead(code,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
 if(url.pathname==='/auth/me')return reply(200,{id:user,nome:'Operador',email:'fixture@example.com',perfil:role,ativo:true});
 if(url.pathname==='/filiais')return reply(200,[{id:unit,nome:'Unidade fictícia',fuso_horario:'America/Recife'}]);
 if(url.pathname==='/usuarios/barbeiros')return reply(200,[{id:user,nome:'Profissional fictício'}]);
 if(url.pathname===`/repasses/profissionais/${user}`) {
  if(falharConsulta) return reply(503,{});
  return reply(200,{gerada:'10.00',liberada:'10.00',pendente:'0.00',elegivel:'10.00',
   deficit_pago:'0.00',bloqueado:false,itens:[],parcelas:[],fechamentos:[],pagamentos:[],estornos:[]});
 }
 if(url.pathname===`/repasses/profissionais/${user}/fechamentos` && req.method==='POST') {
  repassesEnviados++;chaveRepasse=req.headers['idempotency-key'];return reply(504,{});
 }
 if(url.pathname===`/repasses/profissionais/${user}/operacao`) {
  assert.equal(req.headers['idempotency-key'],chaveRepasse);
  if(mostrarRepasse) falharConsulta=true;
  return reply(200,{id:mostrarRepasse?id:null});
 }
 if(url.pathname==='/comandas/painel')return reply(200,{itens:[detail()],total:1,pagina:1,tamanho:6,indicadores:{contagens:{aberta:closed?0:1,fechada:0,pendente:0,cancelada:closed?1:0},valor_abertas:'0.00',pagamentos_disponiveis:true}});
 if(url.pathname===`/comandas/${id}`)return reply(200,detail());
 if(url.pathname.endsWith('/financeiro'))return reply(200,{comanda_id:id,filial_id:unit,situacao:'aberto',total:'0.00',recebido_liquido:'0.00',pagamentos:'0.00',estornos:'0.00',saldo:'0.00',historico:{pagamentos:[],estornos:[]}});
 if(url.pathname.endsWith('/itens/alteracoes')||url.pathname.endsWith('/beneficios'))return reply(200,[]);
 if(req.method==='POST'&&url.pathname.endsWith('/cancelamento')){
  assert.ok(['admin','recepcao'].includes(role));assert.equal(body.confirmado,true);assert.ok(body.motivo.trim());assert.equal(url.searchParams.get('filial_id'),unit);
  posts.push({body,key:req.headers['idempotency-key']});
  if(rejeitar) return reply(409,{detail:{codigo:'versao_itens_desatualizada'}});
  if(!cancellation){assert.equal(body.versao,version);version++;closed=true;cancellation={comanda_id:id,filial_id:unit,registrado_por:user,registrado_em:'2026-11-17T12:00:00Z',motivo:body.motivo,chave_idempotencia:req.headers['idempotency-key'],versao:version,status:'cancelada',status_anterior:'aberta'};}
  else {assert.deepEqual(posts.at(-1),posts.at(-2));}
  if(loseResponse) return reply(504,{});
  return reply(200,cancellation);
 }
 return reply(404,{});
});
let vite,firefox,ws;
async function wait(check,label){const end=Date.now()+20000;while(Date.now()<end){if(await check())return;await new Promise(resolve=>setTimeout(resolve,100));}throw Error('Tempo excedido: '+label);}
try{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const api=server.address().port;
 vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5179','--strictPort'],{cwd:root,env:{...process.env,VITE_API_URL:`http://127.0.0.1:${api}`},stdio:'ignore'});
 await wait(async()=>{try{return (await fetch('http://127.0.0.1:5179')).ok;}catch{return false;}},'Vite');
 firefox=spawn(process.env.FIREFOX_BIN || 'firefox',['--headless','--no-remote','--profile',profile,'--remote-debugging-port','9239'],{stdio:'ignore',env:{...process.env,MOZ_DISABLE_CONTENT_SANDBOX:'1'}});
 await wait(async()=>{try{await fetch('http://127.0.0.1:9239/');return true;}catch{return false;}},'Firefox');
 ws=new WebSocket('ws://127.0.0.1:9239/session');await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 let seq=0;const pending=new Map();ws.addEventListener('message',({data})=>{const b=JSON.parse(data),p=pending.get(b.id);if(p){clearTimeout(p.timer);pending.delete(b.id);b.type==='error'?p.reject(Error(b.message)):p.resolve(b.result);}});
 const cmd=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error(method));},25000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});
 await cmd('session.new',{capabilities:{alwaysMatch:{}}});const {context}=await cmd('browsingContext.create',{type:'tab'});
 const ev=async expression=>{const x=await cmd('script.evaluate',{expression,target:{context},awaitPromise:true});if(x.type==='exception')throw Error(x.exceptionDetails.text);return x.result.value;};
 const section='.comanda-cancelamento',button=async text=>{await wait(()=>ev(`[...document.querySelectorAll('${section} button')].some(b=>b.textContent===${JSON.stringify(text)}&&!b.disabled)`),text);await ev(`[...document.querySelectorAll('${section} button')].find(b=>b.textContent===${JSON.stringify(text)}).click()`);};
 async function open(){
  if (await ev('location.origin') !== 'http://127.0.0.1:5179') {
   await cmd('browsingContext.navigate',{context,url:'http://127.0.0.1:5179/login',wait:'none'});
   await wait(()=>ev("location.origin==='http://127.0.0.1:5179' && document.readyState!=='loading'"),'login');
  }
  await ev(`localStorage.setItem('token','fixture');localStorage.setItem('relaxabarber:filial:${user}','${unit}')`);
  await cmd('browsingContext.navigate',{context,url:'http://127.0.0.1:5179/comandas',wait:'interactive'});await wait(()=>ev(`!!document.querySelector('.comanda-card footer button')`),'Card');await ev(`document.querySelector('.comanda-card footer button').click()`);await wait(()=>ev(`!!document.querySelector('${section}')`),'Cancelamento');
 }
 async function fill(){await button('Cancelar comanda vazia');assert.equal(await ev(`document.querySelector('${section} button[type=submit]').disabled`),true);await ev(`(()=>{const e=document.querySelector('${section} textarea');Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e),'value').set.call(e,'Comanda vazia conferida');e.dispatchEvent(new Event('input',{bubbles:true}));})()`);assert.equal(await ev(`document.querySelector('${section} button[type=submit]').disabled`),true);await ev(`document.querySelector('${section} input[type=checkbox]').click()`);}
 await open();await fill();await button('Voltar sem cancelar');assert.equal(posts.length,0);assert.equal(closed,false);
 rejeitar=true;await fill();await button('Confirmar cancelamento da comanda');
 await wait(()=>ev(`document.querySelector('${section} [role=alert]')?.textContent.includes('mudaram')`),'rejeição');
 assert.equal(await ev(`document.querySelector('${section} textarea').value`),'Comanda vazia conferida');
 await button('Voltar sem cancelar');rejeitar=false;posts.length=0;
 await fill();await button('Confirmar cancelamento da comanda');await wait(()=>ev(`document.querySelector('${section}').textContent.includes('Comanda cancelada em')`),'Auditoria');assert.equal(posts.length,1);assert.equal(version,1);assert.equal(detail().atendimento.status,'aguardando');
 assert.equal(await ev(`[...document.querySelectorAll('dialog button')].some(b=>b.textContent==='Cancelar comanda vazia')`),false);
 console.log('PASS Firefox: motivo, confirmação explícita, voltar sem persistência, cancelamento e auditoria; agendamento preservado');
 closed=false;version=0;cancellation=null;posts.length=0;loseResponse=true;await open();await fill();await button('Confirmar cancelamento da comanda');
 await wait(()=>ev(`document.querySelector('${section}').textContent.includes('Recuperar cancelamento original')`),'Recuperacao');
 loseResponse=false;await open();await button('Recuperar cancelamento original');await wait(()=>ev(`document.querySelector('${section}').textContent.includes('Comanda cancelada em')`),'Replay');
 assert.equal(version,1);assert.ok(posts.length>=2);for(const post of posts) assert.deepEqual(post,posts[0]);
 console.log('PASS Firefox: resposta perdida após aplicação, recarga e replay original sem duplicação');
 for(const perfil of ['barbeiro','barbeiro_chefe']){role=perfil;closed=false;cancellation=null;await open();assert.equal(await ev(`document.querySelectorAll('${section} button').length`),0);}
 console.log('PASS Firefox: barbeiro e barbeiro chefe sem botão de cancelamento');
 role='admin';
 await cmd('browsingContext.navigate',{context,url:'http://127.0.0.1:5179/repasses',wait:'interactive'});
 const btnRepasse=async texto=>{
  const localizar=`[...document.querySelectorAll('main button')].find(b=>b.textContent===${JSON.stringify(texto)}&&!b.disabled)`;
  await wait(()=>ev(`!!(${localizar})`),texto);await ev(`(${localizar}).click()`);
 };
 await wait(()=>ev(`!!document.querySelector('.repasse-filtros select option[value="${user}"]')`),'profissional do repasse');
 await ev(`(()=>{const e=document.querySelector('.repasse-filtros select');e.value='${user}';e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
 await btnRepasse('Fechar período');await btnRepasse('Conferir operação');
 const escritasAntesDaConsulta=repassesEnviados;
 await wait(()=>ev("document.body.innerText.includes('A operação ainda não foi localizada')"),'pendência mantida');
 mostrarRepasse=true;await btnRepasse('Conferir operação');
 await wait(()=>ev("document.body.innerText.includes('Fechamento do período confirmado.') && document.body.innerText.includes('Não foi possível consultar o demonstrativo.')"),'confirmação separada da falha de consulta');
 assert.ok(escritasAntesDaConsulta>=1);assert.equal(repassesEnviados,escritasAntesDaConsulta);
 console.log('PASS Firefox: repasse conferido por GET sem novo POST após 504; falha de consulta preserva sucesso.');
 await cmd('session.end');
}finally{ws?.close();firefox?.kill();vite?.kill();server.closeAllConnections();await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:150});}
