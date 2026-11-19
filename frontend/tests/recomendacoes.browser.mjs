/** Firefox real com API simulada, sem acesso à rede externa nem reservas. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url));
const perfil=await mkdtemp(join(tmpdir(),'rb-recomendacoes-'));
const filial='11111111-1111-4111-8111-111111111111';
const servico='22222222-2222-4222-8222-222222222222';
const barbeiro='33333333-3333-4333-8333-333333333333';
const server=createServer((req,res)=>{
  res.setHeader('Access-Control-Allow-Origin','*');
  const url=new URL(req.url,'http://localhost'); let data;
  if(url.pathname==='/publico/filiais')data=[{id:filial,nome:'Filial QA',endereco:'Rua fictícia'}];
  else if(url.pathname===`/publico/filiais/${filial}/servicos`)data=[{id:servico,nome:'Corte QA',preco:40,tempo_estimado:30,ativo:true}];
  else if(url.pathname==='/publico/barbeiros')data=[{id:barbeiro,nome:'Profissional QA'}];
  else if(url.pathname==='/publico/horarios')data={data:'2099-05-20',duracao:30,fuso:'America/Recife',horarios:['09:00','09:15','09:30','09:45'],recomendados:['09:00','09:30','09:45']};
  else {res.writeHead(404);res.end();return;}
  res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(data));
});
const listen=s=>new Promise(r=>s.listen(0,'127.0.0.1',()=>r(s.address().port)));
async function freePort(){const s=createServer(),p=await listen(s);await new Promise(r=>s.close(r));return p;}
async function waitFor(check,label){const end=Date.now()+20000;while(Date.now()<end){if(await check().catch(()=>false))return;await new Promise(r=>setTimeout(r,100));}throw Error(`Timeout: ${label}`);}
let vite,firefox,ws;
try {
  const api=await listen(server),port=await freePort(),debug=await freePort(),origin=`http://127.0.0.1:${port}`;
  vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:root,env:{...process.env,VITE_API_URL:`http://127.0.0.1:${api}`},stdio:'ignore'});
  await waitFor(async()=> (await fetch(origin)).ok,'Vite');
  firefox=spawn(process.env.FIREFOX_BIN||'firefox',['--headless','--no-remote','--profile',perfil,'--remote-debugging-port',String(debug)],{stdio:'ignore'});
  await waitFor(async()=>{await fetch(`http://127.0.0.1:${debug}`);return true;},'Firefox');
  ws=new WebSocket(`ws://127.0.0.1:${debug}/session`);await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
  let seq=0;const pending=new Map();
  ws.addEventListener('message',({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.type==='error'?p.reject(Error(m.error)):p.resolve(m.result);}});
  function cmd(method,params={}){return new Promise((resolve,reject)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error(method));},20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
  await cmd('session.new',{capabilities:{alwaysMatch:{}}});const {context}=await cmd('browsingContext.create',{type:'tab'});
  async function evaluate(expression){const r=await cmd('script.evaluate',{expression,target:{context},awaitPromise:true});if(r.type==='exception')throw Error(r.exceptionDetails.text);return r.result.value;}
  const text=t=>waitFor(()=>evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`),t);
  const click=async selector=>{await waitFor(()=>evaluate(`!!document.querySelector(${JSON.stringify(selector)})`),selector);await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);};
  await cmd('browsingContext.navigate',{context,url:origin+'/agendar',wait:'complete'});
  await text('Corte QA');await click('input[type=checkbox]');await click('.publico-passo-acoes .publico-botao');
  await text('Profissional QA');await click('input[name=barbeiro]');
  await waitFor(()=>evaluate("!document.querySelector('.publico-passo-acoes .publico-botao').disabled"),'profissional selecionado');
  await click('.publico-passo-acoes .publico-botao');await text('Qual é o melhor momento?');
  await evaluate("(()=>{const e=document.querySelector('input[type=date]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'2099-05-20');e.dispatchEvent(new Event('input',{bubbles:true}));})()");
  await text('09:15');
  assert.equal(await evaluate("document.querySelectorAll('input[name=horario]').length"),4);
  assert.equal(await evaluate("[...document.querySelectorAll('input[name=horario]')].filter(e=>e.parentElement.textContent.includes('Recomendado')).length"),3);
  assert.equal(await evaluate("[...document.querySelectorAll('input[name=horario]')].find(e=>e.parentElement.textContent.includes('09:15')).parentElement.textContent.includes('Recomendado')"),false);
  await evaluate("[...document.querySelectorAll('input[name=horario]')].find(e=>e.parentElement.textContent.includes('09:15')).click()");
  assert.equal(await evaluate("[...document.querySelectorAll('input[name=horario]')].find(e=>e.parentElement.textContent.includes('09:15')).checked"),true);
  await evaluate("[...document.querySelectorAll('input[name=horario]')].find(e=>e.parentElement.textContent.includes('09:30')).click()");
  assert.equal(await evaluate("[...document.querySelectorAll('input[name=horario]')].find(e=>e.parentElement.textContent.includes('09:30')).checked"),true);
  assert.equal(await evaluate("document.querySelectorAll('input[name=horario]:checked').length"),1);
  console.log('PASS Firefox: três recomendações exibidas, todos os horários preservados e seleção livre.');
  await cmd('session.end');
} finally {
  ws?.close();vite?.kill('SIGTERM');firefox?.kill('SIGTERM');server.closeAllConnections();await new Promise(r=>server.close(r));
  await new Promise(r=>setTimeout(r,300));await rm(perfil,{recursive:true,force:true});
}
