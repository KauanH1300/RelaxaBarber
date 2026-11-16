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
const users = [{ ...admin }, { ...admin, id: '20000000-0000-4000-8000-000000000002', nome: 'Profissional teste', email: 'profissional@example.com', perfil: 'barbeiro' }];
const links = [{ id: 'vinculo', usuario_id: users[1].id, filial_id: filial.id, ativo: true }];
const calls = [];
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, PUT, OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  const path = new URL(req.url, 'http://local').pathname;
  const reply = (status, data) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
  if (path === '/auth/me') return reply(200, { ...admin, perfil: role });
  if (path === '/filiais') return reply(200, [filial]);
  if (role !== 'admin') return reply(403, { detail: 'Sem permissão' });
  if (path === '/usuarios' && req.method === 'GET') return reply(200, users);
  if (path === `/filiais/${filial.id}/usuarios` && req.method === 'GET') return reply(200, links);
  let raw = ''; for await (const chunk of req) raw += chunk;
  const data = raw ? JSON.parse(raw) : {};
  calls.push({ path, method: req.method, data });
  if (atraso) await new Promise(r => setTimeout(r, atraso));
  if (bloquear) return reply(409, { detail: 'Há agendamentos futuros ativos ou atendimentos em andamento nesta filial' });
  if (path === '/usuarios' && req.method === 'POST') { const user = { ...data, id: '20000000-0000-4000-8000-000000000003', ativo: true }; delete user.senha; delete user.filial_ids; users.push(user); return reply(201, user); }
  if (path.startsWith('/usuarios/') && req.method === 'PATCH') { const user = users.find(u => u.id === path.split('/').at(-1)); Object.assign(user, data); return reply(200, user); }
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
  await command('browsingContext.navigate', { context, url: `${origin}/login`, wait: 'complete' });
  await evaluate("localStorage.setItem('token','token-ficticio')");
  const navigate = () => command('browsingContext.navigate', { context, url: `${origin}/funcionarios`, wait: 'complete' });
  await navigate(); await text('Profissional teste');
  for (const width of [1440, 768, 320]) { await command('browsingContext.setViewport', { context, viewport: { width, height: 1000 } }); assert.ok(await evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth'), `sem overflow global ${width}`); }
  await click('.funcionarios header button'); await text('Novo funcionário');
  const form = '.funcionario-form';
  await fill(`${form} input[autocomplete="name"]`, 'Funcionária nova');
  await fill(`${form} input[type="email"]`, 'nova@example.com');
  await fill(`${form} input[type="password"]`, 'senha-ficticia');
  await fill(`${form} select`, 'recepcao');
  await click(`${form} button[type="submit"]`); await text('Selecione ao menos uma filial.'); assert.equal(calls.length, 0);
  await click(`${form} input[type="checkbox"]`); atraso = 400;
  await evaluate(`document.querySelector('${form}').requestSubmit();document.querySelector('${form}').requestSubmit()`);
  await text('Funcionário salvo com sucesso.'); atraso = 0;
  assert.equal(calls.filter(c => c.method === 'POST').length, 1);
  assert.deepEqual(calls[0].data.filial_ids, [filial.id]);
  await text('Funcionária nova'); await click('[aria-label="Editar Funcionária nova"]');
  await fill(`${form} input[autocomplete="name"]`, 'Funcionária editada');
  await click(`${form} button[type="submit"]`); await text('Funcionária editada');
  await click('[aria-label="Editar Profissional teste"]'); bloquear = true;
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
  await text('Sem vínculo ativo'); assert.equal(links[0].ativo, false);
  await click('[aria-label="Vínculos com filiais"] li button'); await text('Vínculo ativo');
  for (const perfil of ['recepcao', 'barbeiro', 'barbeiro_chefe']) {
    role = perfil; await navigate(); await text('Somente administradores');
    assert.equal(await evaluate('!!document.querySelector(".funcionarios-tabela")'), false);
    assert.equal(await evaluate(`!!document.querySelector('nav a[href="/funcionarios"]')`), false);
  }
  console.log('PASS funcionários: cadastro, validação de filial, clique duplo, edição, conflito de inativação, vínculos, quatro perfis e 320px; Firefox com API simulada.');
  await command('session.end');
} finally {
  ws?.close(); vite?.kill('SIGTERM'); firefox?.kill('SIGTERM'); server.closeAllConnections(); await new Promise(r => server.close(r));
  await new Promise(r => setTimeout(r, 300)); await rm(profile, { recursive: true, force: true });
}
