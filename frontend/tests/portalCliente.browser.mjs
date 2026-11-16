/** Firefox real com API simulada no loopback; sem banco ou credenciais reais. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'rb-portal-cliente-'));
let entrega=true,ativa=false,sessao=false,senhaAtual='Senha-ficticia-123',pedido=0,trocaEtapa='atual',recente=true;
const calls=[];
const server=createServer(async(req,res)=>{
  res.setHeader('Access-Control-Allow-Origin',req.headers.origin || 'http://127.0.0.1');
  res.setHeader('Access-Control-Allow-Credentials','true');
  res.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type');
  res.setHeader('Access-Control-Allow-Methods','GET, POST, OPTIONS');
  if(req.method==='OPTIONS'){res.writeHead(204);res.end();return;}
  const path=new URL(req.url,'http://local').pathname;
  const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(data===undefined?'':JSON.stringify(data));};
  if(!path.startsWith('/portal-clientes'))return reply(401,{detail:'Não autenticado'});
  calls.push({path,authorization:req.headers.authorization});
  let raw='';for await(const chunk of req)raw+=chunk;const data=raw?JSON.parse(raw):{};
  if(path.startsWith('/portal-clientes/troca-email')&&!sessao)return reply(401,{detail:'Entre na sua conta de cliente.'});
  if(path.startsWith('/portal-clientes/troca-email')&&!recente)return reply(403,{detail:'Confirme sua identidade entrando novamente.'});
  if(path==='/portal-clientes/troca-email'){assert.equal(data.email,undefined);return reply(202,{solicitacao_id:'troca',mensagem:'Confirme o e-mail atual.'});}
  if(path.startsWith('/portal-clientes/troca-email/confirmar-')){
    if(data.codigo!==(trocaEtapa==='atual'?'123456':'654321'))return reply(400,{detail:'Código inválido ou expirado.'});
    if(trocaEtapa==='atual'){trocaEtapa='novo';return reply(200,{mensagem:'Confirme o novo e-mail.'});}
    sessao=false;return reply(200,{mensagem:'E-mail atualizado. As sessões anteriores foram encerradas.'});
  }
  if(path.endsWith('/me'))return sessao && req.headers.cookie?.includes('rb_cliente_sessao=')?reply(200,{id:'cliente',nome:'Cliente Portal',telefone:'5511999991234',email:'cliente@example.com'}):reply(401,{detail:'Entre na sua conta de cliente.'});
  if(path.endsWith('/cadastro')||path.endsWith('/recuperar')){
    if(!entrega)return reply(503,{detail:'O envio de códigos está indisponível. Tente mais tarde ou contate a recepção.'});
    pedido++;await new Promise(r=>setTimeout(r,250));return reply(202,{solicitacao_id:'pedido-'+pedido,mensagem:'Se o pedido for válido, use o código enviado ao e-mail informado.'});
  }
  if(path.endsWith('/ativar')||path.endsWith('/redefinir')){
    if(data.codigo!=='123456')return reply(400,{detail:'Código inválido, expirado ou pedido indisponível.'});
    ativa=true;if(data.senha){senhaAtual=data.senha;sessao=false;}
    return reply(200,{mensagem:data.senha?'Senha redefinida. Entre novamente.':'Conta ativada. Entre com seu e-mail e senha.'});
  }
  if(path.endsWith('/login')){
    if(!ativa || data.senha!==senhaAtual)return reply(401,{detail:'E-mail ou senha inválidos.'});
    sessao=true;recente=true;res.setHeader('Set-Cookie','rb_cliente_sessao=sessao-ficticia; HttpOnly; Path=/portal-clientes; SameSite=Strict');return reply(200,{mensagem:'Login realizado.'});
  }
  if(path.endsWith('/logout')){sessao=false;res.setHeader('Set-Cookie','rb_cliente_sessao=; Max-Age=0; HttpOnly; Path=/portal-clientes; SameSite=Strict');return reply(204);}
  return reply(404,{});
});
const listen = s => new Promise(r => s.listen(0, '127.0.0.1', () => r(s.address().port)));
async function freePort() { const s = createServer(); const p = await listen(s); await new Promise(r => s.close(r)); return p; }
async function waitFor(check, label) { const end = Date.now() + 20000; while (Date.now() < end) { if (await check().catch(() => false)) return; await new Promise(r => setTimeout(r, 100)); } throw new Error(`Timeout: ${label}`); }
let vite, firefox, ws;
try {
  const apiPort = await listen(server), port = await freePort(), debug = await freePort();
  const origin = `http://127.0.0.1:${port}`;
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, env: { ...process.env, VITE_API_URL: `http://127.0.0.1:${apiPort}` }, stdio: 'ignore' });
  await waitFor(async () => (await fetch(origin)).ok, 'Vite');
  firefox = spawn(process.env.FIREFOX_BIN || 'firefox', ['--headless', '--no-remote', '--profile', profile, '--remote-debugging-port', String(debug)], { stdio: 'ignore' });
  await waitFor(async () => { await fetch(`http://127.0.0.1:${debug}`); return true; }, 'Firefox');
  ws = new WebSocket(`ws://127.0.0.1:${debug}/session`);
  await new Promise((r, j) => { ws.addEventListener('open', r, { once: true }); ws.addEventListener('error', j, { once: true }); });
  let sequence = 0; const pending = new Map();
  ws.addEventListener('message', ({ data }) => { const b = JSON.parse(data), p = pending.get(b.id); if (p) { clearTimeout(p.timer); pending.delete(b.id); b.type === 'error' ? p.reject(new Error(`${p.method}: ${b.error}: ${b.message}`)) : p.resolve(b.result); } });
  function command(method, params = {}) { const id = ++sequence; return new Promise((resolve, reject) => { const timer = setTimeout(() => { pending.delete(id); reject(new Error(method)); }, 20000); pending.set(id, { resolve, reject, timer, method }); ws.send(JSON.stringify({ id, method, params })); }); }
  await command('session.new', { capabilities: { alwaysMatch: {} } });
  const { context } = await command('browsingContext.create', { type: 'tab' });
  async function evaluate(expression) { const r = await command('script.evaluate', { expression, target: { context }, awaitPromise: true }); if (r.type === 'exception') throw new Error(r.exceptionDetails.text); return r.result.value; }
  const click = async s => { await waitFor(() => evaluate(`!!document.querySelector(${JSON.stringify(s)})`), s); return evaluate(`document.querySelector(${JSON.stringify(s)}).click()`); };
  const text = t => waitFor(() => evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`), t);
  async function fill(selector, value) { await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e instanceof HTMLSelectElement?'change':'input',{bubbles:true}));})()`); }
  await command('browsingContext.navigate', { context, url: `${origin}/login`, wait: 'complete' });
  await evaluate("localStorage.setItem('token','token-ficticio')");
  const navigate = () => command('browsingContext.navigate', { context, url: `${origin}/cliente`, wait: 'complete' });
  await evaluate("localStorage.setItem('token','token-funcionario-nao-enviar')");
  await navigate();await text('Entre na sua conta');
  await click('a[href="/cliente/cadastro"]');await text('Crie sua conta');
  for(const width of [1440,768,320]){await command('browsingContext.setViewport',{context,viewport:{width,height:1000}});assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`portal sem overflow ${width}`);}
  await fill('input[autocomplete="name"]','Cliente Portal');await fill('input[type="tel"]','11999991234');await fill('input[type="email"]','cliente@example.com');await fill('input[type="password"]',senhaAtual);
  await evaluate("document.querySelector('form').requestSubmit();document.querySelector('form').requestSubmit()");
  await text('Confirme seu e-mail');assert.equal(pedido,1,'pedido duplicado bloqueado');
  await fill('input[autocomplete="one-time-code"]','000000');await click('button[type="submit"]');await text('Código inválido');
  await fill('input[autocomplete="one-time-code"]','123456');await click('button[type="submit"]');await text('Conta ativada.');
  await fill('input[type="email"]','cliente@example.com');await fill('input[type="password"]',senhaAtual);await click('button[type="submit"]');await text('Olá, Cliente Portal');
  assert.equal(await evaluate("document.cookie.includes('rb_cliente_sessao')"),false,'cookie HttpOnly');
  assert.ok(calls.every(c=>c.authorization===undefined),'token da equipe não enviado ao portal');
  await click('a[href="/cliente/conta"]');await text('Minha conta');
  await click('a[href="/cliente/recuperar"]');await text('Recupere seu acesso');
  await fill('input[type="email"]','cliente@example.com');await click('button[type="submit"]');await text('Defina sua nova senha');
  await fill('input[autocomplete="one-time-code"]','123456');await fill('input[type="password"]','Outra-senha-ficticia-123');await click('button[type="submit"]');await text('Senha redefinida.');
  await navigate();await text('Entre na sua conta');
  await fill('input[type="email"]','cliente@example.com');await fill('input[type="password"]',senhaAtual);await click('button[type="submit"]');await text('Olá, Cliente Portal');
  await evaluate("[...document.querySelectorAll('header button')].find(b=>b.textContent==='Sair').click()");await text('Entre na sua conta');
  await navigate();await text('Entre na sua conta');
  assert.equal(await evaluate("!!document.querySelector('a[href=\"/cliente/trocar-email\"]')"),false,'troca ausente no acesso publico');
  await command('browsingContext.navigate',{context,url:`${origin}/cliente/trocar-email`,wait:'complete'});await text('Entre na sua conta');
  await fill('input[type="email"]','cliente@example.com');await fill('input[type="password"]',senhaAtual);await click('button[type="submit"]');await text('Olá, Cliente Portal');
  await click('a[href="/cliente/conta"]');await text('Minha conta');
  await click('a[href="/cliente/trocar-email"]');await text('Alterar e-mail');await text('E-mail atual confirmado');
  recente=false;await fill('input[type="email"]','novo@example.com');await click('button[type="submit"]');await text('Confirme sua identidade entrando novamente');
  assert.ok(await evaluate("document.querySelector('fieldset').disabled"),'sessao antiga impede repeticao');
  await click('a[href="/cliente/entrar"]');await text('Entre na sua conta');
  await fill('input[type="email"]','cliente@example.com');await fill('input[type="password"]',senhaAtual);await click('button[type="submit"]');await text('Olá, Cliente Portal');
  await click('a[href="/cliente/conta"]');await click('a[href="/cliente/trocar-email"]');await text('E-mail atual confirmado');
  for(const width of [1440,768,320]){await command('browsingContext.setViewport',{context,viewport:{width,height:1000}});assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),`troca sem overflow ${width}`);}
  await fill('input[autocomplete="off"]','novo@example.com');await click('button[type="submit"]');await text('Confirme o e-mail atual');
  await fill('input[autocomplete="one-time-code"]','000000');await click('button[type="submit"]');await text('Código inválido');
  await fill('input[autocomplete="one-time-code"]','123456');await click('button[type="submit"]');await text('Confirme o novo e-mail');
  await fill('input[autocomplete="one-time-code"]','654321');await click('button[type="submit"]');await text('E-mail atualizado');
  assert.ok(await evaluate("!!document.querySelector('a[href=\"/cliente/recuperar\"]')"));
  await click('a[href="/cliente/entrar"]');
  entrega=false;await click('a[href="/cliente/cadastro"]');await text('Crie sua conta');
  await fill('input[autocomplete="name"]','Cliente Portal');await fill('input[type="tel"]','11999991234');await fill('input[type="email"]','cliente@example.com');await fill('input[type="password"]','Senha-ficticia-123');await click('button[type="submit"]');await text('O envio de códigos está indisponível');
  assert.equal(await evaluate("!!document.querySelector('input[autocomplete=one-time-code]')"),false,'ausência de entrega não avança verificação');
  console.log('PASS portal clientes Firefox: troca nas configuracoes com sessao obrigatoria, reautenticacao, dois codigos, login, recuperacao, logout e 1440/768/320px; API simulada.');
  await command('session.end');
} finally {
  ws?.close(); vite?.kill('SIGTERM'); firefox?.kill('SIGTERM'); server.closeAllConnections(); await new Promise(r => server.close(r));
  await new Promise(r => setTimeout(r, 300)); await rm(profile, { recursive: true, force: true });
}
