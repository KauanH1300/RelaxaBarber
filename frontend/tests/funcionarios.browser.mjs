/** Firefox real com API simulada no loopback; sem banco ou credenciais reais. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'rb-funcionarios-'));
const filial = { id: '10000000-0000-4000-8000-000000000001', nome: 'Unidade teste', fuso_horario: 'America/Recife' };
const admin = { id: '20000000-0000-4000-8000-000000000001', nome: 'Admin teste', email: 'admin@example.com', telefone: null, perfil: 'admin', ativo: true };
let role = 'admin', bloquear = false, atraso = 0;
let duasFiliais=false;
const outraFilial={...filial,id:'10000000-0000-4000-8000-000000000002',nome:'Outra filial'};
const restricoes={};
const servicos=[{id:'corte',nome:'Corte',ativo:true},{id:'barba',nome:'Barba',ativo:true}];
const users = [{ ...admin }, { ...admin, id: '20000000-0000-4000-8000-000000000002', nome: 'Profissional teste', email: 'profissional@example.com', perfil: 'barbeiro' }];
const links = [{ id: 'vinculo', usuario_id: users[1].id, filial_id: filial.id, ativo: true }];
const calls = [];
let perderResposta = false;
let cadastro;
const jornadas = {};
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type, Idempotency-Key');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  const path = new URL(req.url, 'http://local').pathname;
  const reply = (status, data) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
  if (path === '/auth/me') return reply(200, { ...admin, perfil: role });
  if (path === '/filiais') return reply(200, duasFiliais?[filial,outraFilial]:[filial]);
  if (role !== 'admin') return reply(403, { detail: 'Sem permissão' });
  if (path.startsWith('/usuarios/cadastros/')) return cadastro?.chave === path.split('/').at(-1) ? reply(200, cadastro.user) : reply(404, {});
  if (path.endsWith('/jornada') && req.method === 'GET') return reply(200, jornadas[path] ?? { configurado: false });
  if(path.endsWith('/restricoes-servicos')&&req.method==='GET')return reply(200,{servicos,restricoes:restricoes[path]||[]});
  if (path === '/usuarios' && req.method === 'GET') return reply(200, users);
  if (path === `/filiais/${filial.id}/usuarios` && req.method === 'GET') return reply(200, links);
  if (path === `/filiais/${outraFilial.id}/usuarios` && req.method === 'GET') return reply(200, []);
  let raw = ''; for await (const chunk of req) raw += chunk;
  const data = raw ? JSON.parse(raw) : {};
  calls.push({ path, method: req.method, data });
  if (atraso) await new Promise(r => setTimeout(r, atraso));
  if (bloquear) return reply(409, { detail: 'Há agendamentos futuros ativos ou atendimentos em andamento nesta filial' });
  const escrita = (status, result) => { const incerta = perderResposta; perderResposta = false; return reply(incerta ? 408 : status, result); };
  if (path.endsWith('/jornada') && req.method === 'PUT') { jornadas[path] = { ...data, configurado: true }; return escrita(200, jornadas[path]); }
  if(path.endsWith('/restricoes-servicos')&&req.method==='PUT'){restricoes[path]=data.servicos;return escrita(200,{restricoes:data.servicos});}
  if (path === '/usuarios' && req.method === 'POST') { const user = { ...data, id: '20000000-0000-4000-8000-000000000003', ativo: true }; delete user.senha; delete user.filial_ids; users.push(user); assert.ok(req.headers['idempotency-key']); cadastro = { chave: req.headers['idempotency-key'], user }; return escrita(201, user); }
  if (path.startsWith('/usuarios/') && req.method === 'PATCH') { const user = users.find(u => u.id === path.split('/').at(-1)); Object.assign(user, data); return escrita(200, user); }
  if (path.startsWith('/filiais/') && req.method === 'PUT') { links[0].ativo = data.ativo; return reply(200, links[0]); }
  reply(404, {});
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
  const click = s => evaluate(`document.querySelector(${JSON.stringify(s)}).click()`);
  const text = t => waitFor(() => evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`), t);
  async function fill(selector, value) { await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e instanceof HTMLSelectElement?'change':'input',{bubbles:true}));})()`); }
  await command('browsingContext.navigate', { context, url: `${origin}/login`, wait: 'none' });
  await waitFor(() => evaluate(`location.origin === ${JSON.stringify(origin)} && document.readyState !== 'loading'`), 'login');
  await evaluate("localStorage.setItem('token','token-ficticio')");
  const navigate = () => command('browsingContext.navigate', { context, url: `${origin}/funcionarios`, wait: 'interactive' });
  await navigate(); await text('Profissional teste');
  for (const width of [1440, 768, 320]) { await command('browsingContext.setViewport', { context, viewport: { width, height: 1000 } }); assert.ok(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'), `sem overflow global ${width}`); }
  await click('.funcionarios header button'); await text('Novo funcionário');
  const form = '.funcionario-form';
  await fill(`${form} input[autocomplete="name"]`, 'Funcionária nova');
  await fill(`${form} input[type="email"]`, 'nova@example.com');
  await fill(`${form} input[type="password"]`, 'senha-ficticia');
  await fill(`${form} select`, 'recepcao');
  await click(`${form} button[type="submit"]`); await text('Selecione ao menos uma filial.'); assert.equal(calls.length, 0);
  await click(`${form} input[type="checkbox"]`); atraso = 400; perderResposta = true;
  await evaluate(`document.querySelector('${form}').requestSubmit();document.querySelector('${form}').requestSubmit()`);
  await text('Resultado não confirmado.');
  assert.equal(await evaluate(`document.querySelector('${form} input[type=password]').value`), '');
  assert.equal(await evaluate(`document.querySelector('${form} input[autocomplete=name]').value`), 'Funcionária nova');
  assert.equal(await evaluate("JSON.stringify(sessionStorage).includes('senha-ficticia')"), false);
  await click(`${form}>button:first-of-type`);
  await text('Funcionário salvo com sucesso.'); atraso = 0;
  assert.equal(calls.filter(c => c.method === 'POST').length, 1);
  assert.deepEqual(calls[0].data.filial_ids, [filial.id]);
  await text('Funcionária nova'); await click('[aria-label="Editar Funcionária nova"]');
  await fill(`${form} input[autocomplete="name"]`, 'Funcionária editada');
  perderResposta = true;
  await click(`${form} button[type="submit"]`); await text('Resultado não confirmado.');
  await click(`${form}>button:first-of-type`); await text('Funcionária editada');
  duasFiliais=true;await navigate();await text('Profissional teste');
  await click('[aria-label="Editar Profissional teste"]');await text('Serviços que não realiza');await text('Salvar serviços que não realiza');
  const secao='section[aria-labelledby="restricoes-titulo"]';
  assert.equal(await evaluate(`document.querySelectorAll('${secao} input:checked').length`),0);
  perderResposta = true;
  await click(`${secao} input`);await click(`${secao} button[type=submit]`);await text('Confira as restrições sem descartar');
  await click(`${secao} > button`);await text('As restrições atuais correspondem');
  await click(`${form}>button`);
  const botaoJornada = "[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Jornada')";
  await waitFor(() => evaluate(`(${botaoJornada})?.disabled === false`), 'ação de jornada');
  await evaluate(`(${botaoJornada}).click()`);
  await text('Salvar jornada');
  const jornada = 'section[aria-label="Jornada do barbeiro"]';
  await click(`${jornada} fieldset input[type=checkbox]`);
  perderResposta = true;
  await click(`${jornada} button[type=submit]`); await text('Confira a jornada atual sem descartar');
  await click(`${jornada} > button`); await text('A jornada atual corresponde aos dados enviados.');
  await waitFor(()=>evaluate(`!!document.querySelector('select[aria-label="Filial ativa"] option[value="${outraFilial.id}"]')`),'outra filial carregada');
  await fill('select[aria-label="Filial ativa"]',outraFilial.id);await text('Profissional teste');
  await click('[aria-label="Editar Profissional teste"]');await text('Salvar serviços que não realiza');
  assert.equal(await evaluate(`document.querySelectorAll('${secao} input:checked').length`),0,'excecao nao vaza para outra filial');
  await fill('select[aria-label="Filial ativa"]',filial.id);await text('Profissional teste');
  await click('[aria-label="Editar Profissional teste"]');await text('Salvar serviços que não realiza');
  assert.equal(await evaluate(`document.querySelectorAll('${secao} input:checked').length`),1,'excecao persistida na filial original');
  await click(`${secao} input`);await click(`${secao} button[type=submit]`);await text('Serviços que não realiza salvos nesta filial.');
  assert.deepEqual(calls.filter(c=>c.path.endsWith('/restricoes-servicos')).map(c=>c.data.servicos),[['corte'],[]]);
  bloquear = true;
  await evaluate('window.confirm=()=>false');
  const antes = calls.length;
  await click(`${form} input[type="checkbox"]`); await click(`${form} button[type="submit"]`);
  assert.equal(calls.length, antes, 'cancelar confirmação não envia inativação');
  await evaluate('window.confirm=()=>true'); await click(`${form} button[type="submit"]`);
  await text('Há agendamentos futuros');
  assert.equal(users[1].ativo, true);
  await click(`${form}>button`); bloquear = false;
  await text('Profissional teste'); await click('[aria-label="Filiais de Profissional teste"]');
  await text('Vínculo ativo'); await click('[aria-label="Vínculos com filiais"] li button');
  await waitFor(async()=>links[0].ativo===false,'vinculo desativado');
  await waitFor(()=>evaluate("document.querySelector('[aria-label=\"Vínculos com filiais\"] li button')?.textContent==='Ativar vínculo' && !document.querySelector('[aria-label=\"Vínculos com filiais\"] li button').disabled"),'vinculos atualizados');
  await click('[aria-label="Vínculos com filiais"] li button');await waitFor(async()=>links[0].ativo===true,'vinculo reativado');
  for (const perfil of ['recepcao', 'barbeiro', 'barbeiro_chefe']) {
    role = perfil; await navigate(); await text('Somente administradores');
    assert.equal(await evaluate('!!document.querySelector(".funcionarios-tabela")'), false);
    assert.equal(await evaluate(`!!document.querySelector('nav a[href="/funcionarios"]')`), false);
  }
  console.log('PASS funcionários: excecoes negativas, salvar/editar/limpar, isolamento ao trocar filial, cadastro, clique duplo, edição, conflitos, vínculos, quatro perfis e 320px; API simulada.');
  await command('session.end');
} finally {
  ws?.close(); vite?.kill('SIGTERM'); firefox?.kill('SIGTERM'); server.closeAllConnections(); await new Promise(r => server.close(r));
  await new Promise(r => setTimeout(r, 300)); await rm(profile, { recursive: true, force: true, maxRetries: 8, retryDelay: 150 });
}
