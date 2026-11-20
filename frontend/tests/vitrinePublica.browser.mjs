/** Firefox com API simulada em portas locais efêmeras. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'rb-vitrine-'));
const filial = '10000000-0000-4000-8000-000000000001';
const chamadas = [];
const fisico = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin || '*');
  res.setHeader('Access-Control-Allow-Credentials', 'true');
  const url = new URL(req.url, 'http://local');
  const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
  if (url.pathname === '/publico/filiais') return reply([{ id: filial, nome: 'Unidade QA', fuso_horario: 'America/Recife' }]);
  if (url.pathname === '/publico/filiais/' + filial + '/servicos') return reply([]);
  if (url.pathname === '/portal-clientes/me') return res.writeHead(401).end();
  if (url.pathname === '/publico/filiais/' + filial + '/produtos') {
    const pagina = url.searchParams.get('pagina');
    chamadas.push({ pagina, autenticacao: !!req.headers.authorization });
    return pagina === '2'
      ? reply({ produtos: [{ nome:'Pomada',descricao:null,foto_url:null,preco:'24.00',disponivel:false }], proxima_pagina:null })
      : reply({ produtos: [{ nome:'Óleo de barba',descricao:'Frasco de teste',foto_url:null,preco:'35.50',disponivel:true }], proxima_pagina:2 });
  }
  res.writeHead(404).end();
});
const listen = server => new Promise(r => server.listen(0, '127.0.0.1', () => r(server.address().port)));
async function porta() { const s = createServer(); const p = await listen(s); await new Promise(r => s.close(r)); return p; }
async function espera(verificar, nome) {
  const limite = Date.now() + 15000;
  while (Date.now() < limite) {
    if (await verificar().catch(() => false)) return;
    await new Promise(r => setTimeout(r, 100));
  }
  throw Error('Tempo excedido: ' + nome);
}
let vite, firefox, ws;
try {
  const api = await listen(fisico), site = await porta(), debug = await porta(), origem = 'http://127.0.0.1:' + site;
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(site), '--strictPort'],
    { cwd: root, env: { ...process.env, VITE_API_URL: 'http://127.0.0.1:' + api }, stdio: 'ignore' });
  await espera(async () => (await fetch(origem)).ok, 'Vite');
  firefox = spawn(process.env.FIREFOX_BIN || 'firefox', ['--headless', '--no-remote', '--profile', profile, '--remote-debugging-port', String(debug)], { stdio: 'ignore' });
  await espera(async () => { await fetch('http://127.0.0.1:' + debug); return true; }, 'Firefox');
  ws = new WebSocket('ws://127.0.0.1:' + debug + '/session');
  await new Promise((r, j) => { ws.addEventListener('open', r, { once: true }); ws.addEventListener('error', j, { once: true }); });
  const pendentes = new Map(); let seq = 0;
  ws.addEventListener('message', ({ data }) => {
    const m = JSON.parse(data), p = pendentes.get(m.id);
    if (p) { clearTimeout(p.timer); pendentes.delete(m.id); m.type === 'error' ? p.reject(Error(m.error)) : p.resolve(m.result); }
  });
  const comando = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++seq, timer = setTimeout(() => reject(Error(method)), 15000);
    pendentes.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params }));
  });
  await comando('session.new', { capabilities: { alwaysMatch: {} } });
  const { context } = await comando('browsingContext.create', { type: 'tab' });
  const ir = path => comando('browsingContext.navigate', { context, url: origem + path, wait: 'complete' });
  async function avaliar(expression) {
    const r = await comando('script.evaluate', { expression, target: { context }, awaitPromise: true });
    if (r.type === 'exception') throw Error(r.exceptionDetails.text);
    return r.result.value;
  }
  await ir('/agendar');
  await espera(() => avaliar("[...document.querySelectorAll('a')].some(a=>a.textContent==='Ver produtos da vitrine')"), 'link da vitrine');
  await avaliar("[...document.querySelectorAll('a')].find(a=>a.textContent==='Ver produtos da vitrine').click()");
  await espera(() => avaliar('document.body.textContent.includes("Frasco de teste")'), 'produto da primeira página');
  assert.ok(await avaliar('document.querySelector(".vitrine-placeholder").textContent.includes("Sem foto")'));
  assert.ok(await avaliar('document.body.textContent.includes("Disponível")'));
  await comando('browsingContext.setViewport', { context, viewport: { width: 350, height: 850 } });
  assert.ok(await avaliar('document.documentElement.scrollWidth<=innerWidth'));
  await avaliar('[...document.querySelectorAll(".vitrine button")].find(b=>b.textContent==="Próxima").click()');
  await espera(() => avaliar('document.body.textContent.includes("Pomada")'), 'segunda página');
  assert.ok(await avaliar('document.body.textContent.includes("Indisponível")'));
  assert.deepEqual(chamadas.map(c => c.autenticacao), [false,false]);
  await comando('session.end');
  console.log('PASS Firefox: vitrine sem autenticação, navegação, paginação, placeholder e largura móvel.');
} finally {
  ws?.close(); vite?.kill(); firefox?.kill(); fisico.closeAllConnections();
  await new Promise(r => fisico.close(r));
  await rm(profile, { recursive: true, force: true, maxRetries: 12, retryDelay: 250 });
}
