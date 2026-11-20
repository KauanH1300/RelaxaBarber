/** Apenas navegador e API simulada em loopback. Sem contas ou credenciais reais. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const profile=await mkdtemp(join(tmpdir(),'rb-acesso-'));
const calls=[];
let sessaoExpirada=false;
const server=createServer(async(req,res)=>{
  res.setHeader('Access-Control-Allow-Origin',req.headers.origin||'http://127.0.0.1');
  res.setHeader('Access-Control-Allow-Credentials','true');
  res.setHeader('Access-Control-Allow-Headers','Content-Type, Authorization');
  res.setHeader('Access-Control-Allow-Methods','GET, POST, OPTIONS');
  if(req.method==='OPTIONS'){res.writeHead(204);res.end();return;}
  const path=new URL(req.url,'http://local').pathname;
  let raw='';for await(const chunk of req)raw+=chunk;
  calls.push({path,authorization:req.headers.authorization});
  const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  if(path==='/auth/login'){
    const fields=new URLSearchParams(raw);
    return fields.get('username')==='equipe@example.com'&&fields.get('password')==='Senha-ficticia-123'?reply(200,{access_token:'token-equipe-simulado'}):reply(401,{detail:'Credenciais inválidas.'});
  }
  if(path==='/auth/recuperar')return reply(202,{solicitacao_id:'pedido',mensagem:'Se o pedido for elegível, use o código.'});
  if(path==='/auth/redefinir'){
    const {solicitacao_id,codigo,senha}=JSON.parse(raw);
    return solicitacao_id==='pedido'&&codigo==='123456'&&senha==='Senha-nova-ficticia'
      ? reply(200,{}) : reply(400,{detail:'Código inválido'});
  }
  if(path==='/auth/me'&&sessaoExpirada)return reply(401,{detail:'Não autenticado'});
  if(path==='/auth/me')return reply(200,{id:'equipe',nome:'Equipe teste',perfil:'admin',email:'equipe@example.com'});
  if(path==='/portal-clientes/login')return reply(401,{detail:'Credenciais inválidas.'});
  return reply(200,[]);
});
const listen=s=>new Promise(r=>s.listen(0,'127.0.0.1',()=>r(s.address().port)));
async function freePort(){const s=createServer();const port=await listen(s);await new Promise(r=>s.close(r));return port;}
async function waitFor(check,label){const end=Date.now()+20000;while(Date.now()<end){if(await check().catch(()=>false))return;await new Promise(r=>setTimeout(r,100));}throw Error('Timeout: '+label);}
let vite,firefox,ws;
try{
  const apiPort=await listen(server),port=await freePort(),debug=await freePort(),origin=`http://127.0.0.1:${port}`;
  vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:root,env:{...process.env,VITE_API_URL:`http://127.0.0.1:${apiPort}`},stdio:'ignore'});
  await waitFor(async()=>(await fetch(origin)).ok,'Vite');
  firefox=spawn(process.env.FIREFOX_BIN||'firefox',['--headless','--no-remote','--profile',profile,'--remote-debugging-port',String(debug)],{stdio:'ignore'});
  await waitFor(async()=>{await fetch(`http://127.0.0.1:${debug}`);return true;},'Firefox');
  ws=new WebSocket(`ws://127.0.0.1:${debug}/session`);await new Promise((r,j)=>{ws.addEventListener('open',r,{once:true});ws.addEventListener('error',j,{once:true});});
  let seq=0;const pending=new Map();
  ws.addEventListener('message',({data})=>{const m=JSON.parse(data),p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.type==='error'?p.reject(Error(m.error)):p.resolve(m.result);}});
  function cmd(method,params={}){return new Promise((resolve,reject)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error(method));},20000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
  await cmd('session.new',{capabilities:{alwaysMatch:{}}});const {context}=await cmd('browsingContext.create',{type:'tab'});
  async function evaluate(expression){const r=await cmd('script.evaluate',{expression,target:{context},awaitPromise:true});if(r.type==='exception')throw Error(r.exceptionDetails.text);return r.result.value;}
  const text=t=>waitFor(()=>evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`),t);
  const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const fill=(selector,value)=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await cmd('browsingContext.navigate',{context,url:origin+'/cliente/entrar?retorno=agendamento',wait:'complete'});await text('Bem-vindo de volta');
  await evaluate("sessionStorage.setItem('escolhas-teste','preservar');localStorage.setItem('token','token-anterior')");
  for(const role of ['cliente','equipe']){
    if(role==='equipe'){await click('.acesso-alternancia a:last-child');await text('E-mail Profissional');}
    for(const width of [1440,768,320]){
      await cmd('browsingContext.setViewport',{context,viewport:{width,height:1000}});
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`${role} sem overflow ${width}`);
      assert.ok(await evaluate("document.querySelector('.acesso-alternancia a[aria-current]').textContent.includes("+JSON.stringify(role==='equipe'?'Equipe':'Clientes')+")"));
      assert.ok(await evaluate("[...document.querySelectorAll('label[for]')].every(l=>document.getElementById(l.htmlFor))"));
      assert.ok(await evaluate("getComputedStyle(document.querySelector('.acesso-submit')).backgroundColor==='rgb(212, 175, 55)'"));
      if(process.env.QA_SCREENSHOTS){await evaluate('Promise.all([...document.images].map(i=>i.decode().catch(()=>{})))');const shot=await cmd('browsingContext.captureScreenshot',{context,origin:'viewport'});await writeFile(join(process.env.QA_SCREENSHOTS,`${role}-${width}.png`),Buffer.from(shot.data,'base64'));}
    }
    await fill('input[type=email]',`${role}@example.com`);await fill('input[type=password]','Senha-ficticia-123');
    await click('button[aria-label="Mostrar senha"]');assert.equal(await evaluate("document.querySelector('#acesso-senha').type"),'text');
    await click('button[aria-label="Ocultar senha"]');assert.equal(await evaluate("document.querySelector('#acesso-senha').type"),'password');
    if(role==='cliente'){
      await click('button[type=submit]');await waitFor(()=>evaluate("!!document.querySelector('[role=alert]')"),'erro de login');
      assert.equal(calls.filter(c=>c.path==='/portal-clientes/login').length,1);
      assert.ok(calls.filter(c=>c.path.startsWith('/portal-clientes')).every(c=>!c.authorization));
    }
  }
  assert.ok(await evaluate("location.search==='?retorno=agendamento' && sessionStorage.getItem('escolhas-teste')==='preservar'"));
  await click('.acesso-alternancia a:first-child');await text('Conta de cliente');
  assert.equal(await evaluate("document.querySelector('#acesso-senha').value"),'','nao transfere senha entre perfis');
  assert.ok(await evaluate("document.querySelector('a[href=\"/cliente/recuperar?retorno=agendamento\"]')!==null"));
  await click('.acesso-alternancia a:last-child');await text('E-mail Profissional');
  await fill('input[type=email]','equipe@example.com');await fill('input[type=password]','Senha-ficticia-123');
  await evaluate("document.querySelector('form').requestSubmit();document.querySelector('form').requestSubmit()");
  await waitFor(()=>evaluate("location.pathname==='/agendamentos'"),'destino da equipe');
  assert.equal(calls.filter(c=>c.path==='/auth/login').length,1,'clique duplo sem duplicar login');
  assert.equal(await evaluate("localStorage.getItem('token')"),'token-equipe-simulado');
  assert.ok(calls.some(c=>c.path==='/auth/me'&&c.authorization==='Bearer token-equipe-simulado'));
  sessaoExpirada=true;
  await cmd('browsingContext.navigate',{context,url:origin+'/agendamentos',wait:'complete'});
  await waitFor(()=>evaluate("location.pathname==='/login' && localStorage.getItem('token')===null"),'401 encerra sessão da equipe');
  await click('a[href="/recuperar-senha"]');await text('Recuperar senha');
  await fill('input[type=email]','equipe@example.com');await click('button[type=submit]');
  await text('Redefinir senha da equipe');await fill('input[autocomplete=one-time-code]','123456');
  await fill('input[autocomplete=new-password]:first-of-type','Senha-nova-ficticia');
  await fill('label:last-of-type input[autocomplete=new-password]','Senha-nova-ficticia');
  await click('button[type=submit]');await text('Senha redefinida.');
  console.log('PASS Firefox acesso, expiração e recuperação da equipe com API simulada.');
  await cmd('session.end');
}finally{
  ws?.close();vite?.kill('SIGTERM');firefox?.kill('SIGTERM');server.closeAllConnections();await new Promise(r=>server.close(r));
  await new Promise(r=>setTimeout(r,300));await rm(profile,{recursive:true,force:true,maxRetries:12,retryDelay:250});
}
