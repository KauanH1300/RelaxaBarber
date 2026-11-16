/** Firefox real, apenas API simulada no loopback; nenhuma reserva ou conta real. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const profile=await mkdtemp(join(tmpdir(),'rb-publico-'));
let sessao=false,ativada=false,catalogoFalha=false;
const calls=[];
const server=createServer(async(req,res)=>{
  res.setHeader('Access-Control-Allow-Origin',req.headers.origin||'http://127.0.0.1');
  res.setHeader('Access-Control-Allow-Credentials','true');
  res.setHeader('Access-Control-Allow-Headers','Content-Type');
  res.setHeader('Access-Control-Allow-Methods','GET, POST, OPTIONS');
  if(req.method==='OPTIONS'){res.writeHead(204);res.end();return;}
  const path=new URL(req.url,'http://local').pathname;
  calls.push({path,method:req.method,authorization:req.headers.authorization});
  const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  let raw='';for await(const chunk of req)raw+=chunk;const data=raw?JSON.parse(raw):{};
  if(path==='/servicos/')return catalogoFalha?reply(503,{detail:'Indisponivel'}):reply(200,[{id:'corte',nome:'Corte clássico',preco:40,tempo_estimado:30,ativo:true},{id:'barba',nome:'Barba',preco:25,tempo_estimado:20,ativo:true}]);
  if(path==='/portal-clientes/me')return sessao&&req.headers.cookie?.includes('rb_cliente_sessao=')?reply(200,{id:'cliente-teste',nome:'Cliente teste',email:'cliente@example.com',telefone:'5511999991234'}):reply(401,{detail:'Entre na sua conta de cliente.'});
  if(path==='/portal-clientes/cadastro')return reply(202,{solicitacao_id:'cadastro-teste',mensagem:'Confira seu e-mail.'});
  if(path==='/portal-clientes/ativar'){
    if(data.codigo!=='123456')return reply(400,{detail:'Código inválido.'});
    ativada=true;return reply(200,{mensagem:'Conta ativada. Entre com seu e-mail e senha.'});
  }
  if(path==='/portal-clientes/login'){
    if(!ativada||data.senha!=='Senha-ficticia-longa-123')return reply(401,{detail:'Credenciais inválidas.'});
    sessao=true;res.setHeader('Set-Cookie','rb_cliente_sessao=sessao-ficticia; HttpOnly; Path=/portal-clientes; SameSite=Strict');return reply(200,{mensagem:'Login realizado.'});
  }
  return reply(404,{detail:'Endpoint nao previsto no teste'});
});
const listen=s=>new Promise(r=>s.listen(0,'127.0.0.1',()=>r(s.address().port)));
async function freePort(){const s=createServer();const p=await listen(s);await new Promise(r=>s.close(r));return p;}
async function waitFor(check,label){const end=Date.now()+20000;while(Date.now()<end){if(await check().catch(()=>false))return;await new Promise(r=>setTimeout(r,100));}throw Error('Timeout: '+label);}
let vite,firefox,ws;
try{
  const apiPort=await listen(server),port=await freePort(),debug=await freePort(),origin=`http://127.0.0.1:${port}`;
  vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:root,env:{...process.env,VITE_API_URL:`http://127.0.0.1:${apiPort}`},stdio:'ignore'});
  await waitFor(async()=> (await fetch(origin)).ok,'Vite');
  firefox=spawn(process.env.FIREFOX_BIN||'firefox',['--headless','--no-remote','--profile',profile,'--remote-debugging-port',String(debug)],{stdio:'ignore'});
  await waitFor(async()=>{await fetch(`http://127.0.0.1:${debug}`);return true;},'Firefox');
  ws=new WebSocket(`ws://127.0.0.1:${debug}/session`);await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
  let seq=0;const pending=new Map();
  ws.addEventListener('message',({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.type==='error'?p.reject(Error(m.error)):p.resolve(m.result);}});
  function cmd(method,params={}){return new Promise((resolve,reject)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error(method));},20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
  await cmd('session.new',{capabilities:{alwaysMatch:{}}});const {context}=await cmd('browsingContext.create',{type:'tab'});
  async function evaluate(expression){const r=await cmd('script.evaluate',{expression,target:{context},awaitPromise:true});if(r.type==='exception')throw Error(r.exceptionDetails.text);return r.result.value;}
  const text=t=>waitFor(()=>evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`),t);
  const click=async selector=>{await waitFor(()=>evaluate(`!!document.querySelector(${JSON.stringify(selector)})`),selector);return evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);};
  async function fill(selector,value){await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
  const navigate=path=>cmd('browsingContext.navigate',{context,url:origin+path,wait:'complete'});
  await navigate('/');await text('Corte clássico');
  await evaluate("localStorage.setItem('token','token-funcionario-nao-usar')");
  for(const width of [1440,768,320]){
    await cmd('browsingContext.setViewport',{context,viewport:{width,height:1000}});
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`inicio sem overflow ${width}`);
    if(process.env.QA_SCREENSHOTS){const shot=await cmd('browsingContext.captureScreenshot',{context,origin:'viewport'});await writeFile(join(process.env.QA_SCREENSHOTS,`inicio-${width}.png`),Buffer.from(shot.data,'base64'));}
  }
  assert.equal(calls.some(c=>c.path.startsWith('/portal-clientes')),false,'exploracao sem consulta de autenticacao');
  await click('a[aria-label="Escolher Corte clássico"]');await text('Escolha seu serviço');await text('30 min');
  assert.ok(await evaluate("document.querySelector('input[name=servico]').checked"));
  await click('.publico-passo-acoes .publico-botao');await text('Com quem você prefere?');
  await evaluate("[...document.querySelectorAll('.publico-opcoes label')].find(e=>e.textContent.includes('Rodrigo Relaxa')).querySelector('input').click()");
  await click('.publico-passo-acoes .publico-botao');await text('Qual é o melhor momento?');
  await fill('input[type=date]','2099-05-20');await fill('input[type=time]','13:45');
  await click('.publico-voltar');await text('Com quem você prefere?');await click('.publico-passo-acoes .publico-botao');await text('Qual é o melhor momento?');
  assert.equal(await evaluate("document.querySelector('input[type=time]').value"),'13:45');
  assert.equal(calls.some(c=>c.path.startsWith('/portal-clientes')),false,'sem login antes da confirmacao');
  await click('.publico-passo-acoes .publico-botao');await text('Suas escolhas estão guardadas');
  await click('a[href="/cliente/cadastro?retorno=agendamento"]');await text('Crie sua conta');
  await fill('input[autocomplete=name]','Cliente teste');await fill('input[type=tel]','11999991234');await fill('input[type=email]','cliente@example.com');await fill('input[type=password]','Senha-ficticia-longa-123');await click('button[type=submit]');await text('Confirme seu e-mail');
  assert.ok(await evaluate("location.search.includes('retorno=agendamento')"));
  await fill('input[autocomplete=one-time-code]','123456');await click('button[type=submit]');await text('Conta ativada.');
  await fill('input[type=email]','cliente@example.com');await fill('input[type=password]','Senha-ficticia-longa-123');await click('button[type=submit]');await text('Revise suas preferências');await text('Você está conectado');
  assert.ok(await evaluate("location.pathname==='/agendar' && location.search.includes('confirmacao')"));
  assert.ok(await evaluate("document.querySelector('.publico-resumo').textContent.includes('Corte clássico') && document.querySelector('.publico-resumo').textContent.includes('Rodrigo Relaxa') && document.querySelector('.publico-resumo').textContent.includes('20/05/2099') && document.querySelector('.publico-resumo').textContent.includes('13:45')"));
  assert.ok(await evaluate("[...document.querySelectorAll('button')].some(b=>b.disabled&&b.textContent==='Reserva online em breve')"));
  for(const width of [1440,768,320]){await cmd('browsingContext.setViewport',{context,viewport:{width,height:1000}});assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`agendamento sem overflow ${width}`);}
  await navigate('/agendar?etapa=confirmacao');await text('Você está conectado');await text('13:45');
  assert.ok(await evaluate("!sessionStorage.getItem('rb_agendamento_publico_v1').includes('Senha-ficticia') && !sessionStorage.getItem('rb_agendamento_publico_v1').includes('cliente@example.com') && localStorage.getItem('token')==='token-funcionario-nao-usar'"));
  sessao=false;await navigate('/agendar?etapa=confirmacao');await text('Suas escolhas estão guardadas');
  catalogoFalha=true;await navigate('/agendar');await text('Não foi possível carregar os serviços');
  assert.ok(calls.every(c=>c.authorization===undefined),'nenhum token da equipe');
  assert.ok(calls.every(c=>!c.path.startsWith('/agendamentos')&&!c.path.startsWith('/usuarios')&&!c.path.startsWith('/filiais')),'sem APIs privadas ou reservas');
  console.log('PASS Firefox publico: inicio responsivo 1440/768/320, catalogo real simulado, cinco etapas, navegacao sem login, cadastro/ativacao/login e retorno com escolhas, recarga, confirmacao bloqueada e falha de catalogo; nenhuma reserva.');
  await cmd('session.end');
}finally{
  ws?.close();vite?.kill('SIGTERM');firefox?.kill('SIGTERM');server.closeAllConnections();await new Promise(r=>server.close(r));
  await new Promise(r=>setTimeout(r,300));await rm(profile,{recursive:true,force:true});
}
