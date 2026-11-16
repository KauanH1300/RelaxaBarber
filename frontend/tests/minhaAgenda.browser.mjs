/** Firefox com API simulada; nenhuma reserva, conta ou banco reais. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const profile=await mkdtemp(join(tmpdir(),'rb-minha-agenda-'));
let sessao=false,falhaLista=false,vazio=false,cancelamentos=0,remarcacoes=0,consultas=0;
const base={filial:'Barbearia teste',servicos:[{nome:'Corte',duracao:30,valor:'35.00'}],barbeiro:{id:'prof',nome:'Profissional teste'},data:'2099-05-20',hora_inicio:'10:00:00',hora_fim:'10:30:00',duracao:30,valor:'35.00',status:'pendente',atualizado_em:'2026-11-16T12:00:00Z',proximo:true,pode_cancelar:true,pode_remarcar:true,fuso:'America/Recife'};
const itens=[{...base,id:'cancelar'},{...base,id:'remarcar'},{...base,id:'antigo',data:'2020-01-01',status:'concluido',proximo:false,pode_cancelar:false,pode_remarcar:false}];
const calls=[];
const server=createServer(async(req,res)=>{
  res.setHeader('Access-Control-Allow-Origin',req.headers.origin||'http://127.0.0.1');res.setHeader('Access-Control-Allow-Credentials','true');
  res.setHeader('Access-Control-Allow-Headers','Content-Type');res.setHeader('Access-Control-Allow-Methods','GET, POST, PATCH, OPTIONS');
  if(req.method==='OPTIONS'){res.writeHead(204);res.end();return;}
  const path=new URL(req.url,'http://local').pathname;
  calls.push({path,method:req.method,authorization:req.headers.authorization});
  const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
  let raw='';for await(const c of req)raw+=c;const data=raw?JSON.parse(raw):{};
  if(path==='/portal-clientes/login'){sessao=true;res.setHeader('Set-Cookie','rb_cliente_sessao=teste; HttpOnly; Path=/portal-clientes; SameSite=Strict');return reply(200,{mensagem:'Login realizado.'});}
  if(!sessao||!req.headers.cookie?.includes('rb_cliente_sessao='))return reply(401,{detail:'Entre na sua conta.'});
  if(path==='/portal-clientes/agendamentos')return falhaLista?reply(503,{detail:'Consulta indisponível.'}):reply(200,vazio?[]:itens);
  if(path.endsWith('/opcoes'))return reply(200,{barbeiros:[{id:'prof',nome:'Profissional teste'}],horarios:['14:15','14:45'],fuso:'America/Recife'});
  if(path.endsWith('/cancelamento')){
    assert.deepEqual(Object.keys(data),['atualizado_em_esperado']);cancelamentos++;
    Object.assign(itens[0],{status:'cancelado',proximo:false,pode_cancelar:false,pode_remarcar:false,atualizado_em:'2026-11-16T12:00:01Z'});return reply(200,itens[0]);
  }
  if(path.endsWith('/reagendamento')){
    assert.deepEqual(Object.keys(data).sort(),['atualizado_em_esperado','barbeiro_id','data','hora_inicio']);assert.equal(data.barbeiro_id,null);
    remarcacoes++;
    if(remarcacoes===1)return reply(409,{detail:'Horário ocupado. Consulte o agendamento antes de escolher outra opção.'});
    Object.assign(itens[1],{data:data.data,hora_inicio:data.hora_inicio,hora_fim:'14:45',atualizado_em:'2026-11-16T12:00:02Z'});
    return reply(503,{detail:'Resposta não confirmada.'}); // operation committed, response lost
  }
  if(path==='/portal-clientes/agendamentos/remarcar'){consultas++;return reply(200,itens[1]);}
  return reply(404,{detail:'Não encontrado.'});
});
const listen=s=>new Promise(r=>s.listen(0,'127.0.0.1',()=>r(s.address().port)));
async function freePort(){const s=createServer();const p=await listen(s);await new Promise(r=>s.close(r));return p;}
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
  const button=async(label,section='')=>{await waitFor(()=>evaluate(`[...document.querySelectorAll(${JSON.stringify(section+' button')})].some(b=>b.textContent===${JSON.stringify(label)}&&!b.disabled)`),label);return evaluate(`(()=>{const e=[...document.querySelectorAll(${JSON.stringify(section+' button')})].find(b=>b.textContent===${JSON.stringify(label)});e.click();})()`);};
  const navigate=()=>cmd('browsingContext.navigate',{context,url:origin+'/cliente/agendamentos',wait:'complete'});
  await navigate();await text('Bem-vindo de volta');assert.ok(await evaluate("location.search.includes('retorno=meus-agendamentos')"));
  await evaluate("localStorage.setItem('token','token-equipe-nao-usar')");
  await fill('input[type=email]','cliente@example.com');await fill('input[type=password]','Senha-ficticia-123');await click('button[type=submit]');await text('Próximos agendamentos');await text('Histórico de agendamentos');
  for(const width of [1440,768,320]){await cmd('browsingContext.setViewport',{context,viewport:{width,height:1000}});assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`sem overflow ${width}`);}
  await button('Cancelar agendamento','#agenda-proximos + .agenda-lista');await text('Confirma o cancelamento');await button('Voltar');assert.equal(cancelamentos,0);
  await button('Cancelar agendamento');await button('Confirmar cancelamento');await text('Cancelado');assert.equal(cancelamentos,1);
  assert.equal(await evaluate("document.querySelectorAll('[aria-labelledby=agenda-historico] article').length"),2);
  await button('Remarcar');await text('Nova data');await fill('input[type=date]','2099-05-21');await text('14:15');await click('input[type=radio]');await button('Confirmar remarcação');await text('Horário ocupado.');
  assert.equal(remarcacoes,1);await button('Consultar agendamento atual');await button('Remarcar');await text('14:15');await click('input[type=radio]');
  await evaluate("(()=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent==='Confirmar remarcação');b.click();b.click();})()");
  await text('Resultado não confirmado.');assert.equal(remarcacoes,2);
  await button('Consultar agendamento atual');await text('21/05/2099');assert.equal(remarcacoes,2,'sem repeticao automatica');assert.equal(consultas,2);
  falhaLista=true;await navigate();await text('Consulta indisponível.');falhaLista=false;vazio=true;await button('Consultar novamente');await text('Você não possui próximos agendamentos.');await text('Seu histórico de agendamentos está vazio.');
  assert.ok(calls.every(c=>!c.authorization));assert.ok(calls.every(c=>c.path.startsWith('/portal-clientes/')));
  console.log('PASS Firefox Meus Agendamentos: autenticacao e retorno, proximos/historico, 1440/768/320px, cancelamento confirmado, remarcacao, conflito, resposta incerta consultada sem repeticao, erro e vazio; API simulada.');
  await cmd('session.end');
}finally{
  ws?.close();vite?.kill('SIGTERM');firefox?.kill('SIGTERM');server.closeAllConnections();await new Promise(r=>server.close(r));await new Promise(r=>setTimeout(r,300));await rm(profile,{recursive:true,force:true});
}
