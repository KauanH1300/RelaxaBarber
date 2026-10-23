/** Firefox real + API fictícia local; nunca conecta ao Supabase.
 * Execute em frontend: node tests/comandas.browser.mjs (Node 22+, Firefox instalado).
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'rb-comandas-firefox-'));
const a = '10000000-0000-4000-8000-000000000001', b = '10000000-0000-4000-8000-000000000002';
const own = '20000000-0000-4000-8000-000000000001', other = '20000000-0000-4000-8000-000000000002';
const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Recife' }).format(new Date());
const rows = ['aberta', 'fechada', 'pendente', 'aberta', 'cancelada', 'aberta', 'fechada', 'aberta'].map((status, i) => ({
  id: `30000000-0000-4000-8000-${String(i + 1).padStart(12, '0')}`, agendamento_id: `agendamento-${i}`,
  filial_id: a, cliente_id: `cliente-${i}`, barbeiro_id: i % 2 ? other : own,
  cliente: { id: `cliente-${i}`, nome: `Cliente fictício ${i + 1}` },
  profissional: { id: i % 2 ? other : own, nome: i % 2 ? 'Profissional B' : 'Profissional A' },
  filial: { id: a, nome: 'Unidade A' }, status,
  atendimento: { id: `agendamento-${i}`, data: today, hora_inicio: '09:00:00', hora_fim: '09:30:00', status: status === 'fechada' ? 'concluido' : 'pendente' },
  data_abertura: '2026-10-22T12:00:00Z', data_fechamento: null, total: '55.50',
  itens: [{ id: `item-${i}`, tipo: 'servico', servico_id: 'servico', descricao: 'Serviço de teste', quantidade: 1, preco_unitario: '55.50', subtotal: '55.50' }],
}));
let role = 'admin', panelMode = 'normal', detailMode = 200;
const requests = [];
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type');
  if (req.method === 'OPTIONS') return res.writeHead(204).end();
  const url = new URL(req.url, 'http://localhost');
  requests.push({ path: url.pathname, params: Object.fromEntries(url.searchParams) });
  const reply = (code, body) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
  if (url.pathname === '/auth/me') return reply(200, { id: own, nome: 'Operador fictício', email: 'ui@example.test', perfil: role, ativo: true });
  if (url.pathname === '/filiais') return reply(200, [{ id: a, nome: 'Unidade A', fuso_horario: 'America/Recife' }, { id: b, nome: 'Unidade B', fuso_horario: 'America/Recife' }]);
  if (url.pathname === '/usuarios/barbeiros') return reply(200, [{ id: own, nome: 'Profissional A' }, ...(role === 'barbeiro' ? [] : [{ id: other, nome: 'Profissional B' }])]);
  if (url.pathname === '/comandas/painel') {
    const mode = panelMode;
    if (mode === 'delay') await new Promise((resolve) => setTimeout(resolve, 900));
    if (mode === 'error') return reply(503, { detail: 'Consulta temporariamente indisponível' });
    let data = mode === 'empty' || url.searchParams.get('filial_id') === b ? [] : rows;
    if (role === 'barbeiro') data = data.filter((row) => row.barbeiro_id === own);
    for (const [param, getter] of [['busca', (r) => r.cliente.nome], ['profissional_id', (r) => r.barbeiro_id]]) {
      const value = url.searchParams.get(param); if (value) data = data.filter((row) => getter(row).includes(value));
    }
    if (url.searchParams.get('data_inicio')) data = data.filter((row) => row.atendimento.data >= url.searchParams.get('data_inicio'));
    if (url.searchParams.get('data_fim')) data = data.filter((row) => row.atendimento.data <= url.searchParams.get('data_fim'));
    const contagens = Object.fromEntries(['aberta', 'fechada', 'pendente', 'cancelada'].map((s) => [s, data.filter((row) => row.status === s).length]));
    const indicadores = { contagens, valor_abertas: (contagens.aberta * 55.5).toFixed(2), pagamentos_disponiveis: false };
    if (url.searchParams.get('status')) data = data.filter((row) => row.status === url.searchParams.get('status'));
    const pagina = Number(url.searchParams.get('pagina') || 1), tamanho = Number(url.searchParams.get('tamanho') || 6);
    return reply(200, { itens: data.slice((pagina - 1) * tamanho, pagina * tamanho), pagina, tamanho, total: data.length, indicadores });
  }
  if (url.pathname.startsWith('/comandas/')) return reply(detailMode, detailMode === 200 ? rows.find((row) => row.id === url.pathname.split('/').at(-1)) : { detail: 'Indisponível' });
  return reply(404, {});
});
const listen = (s) => new Promise((resolve, reject) => { s.once('error', reject); s.listen(0, '127.0.0.1', () => resolve(s.address().port)); });
async function freePort() { const s = createServer(); const p = await listen(s); await new Promise((resolve) => s.close(resolve)); return p; }
async function waitFor(check, label) {
  const end = Date.now() + 15000;
  while (Date.now() < end) { try { if (await check()) return; } catch { /* aguarda */ } await new Promise((resolve) => setTimeout(resolve, 100)); }
  throw new Error(`Tempo excedido: ${label}`);
}
let vite, firefox, ws;
try {
  const apiPort = await listen(server), port = await freePort(), debug = await freePort();
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port), '--strictPort'], { cwd: root, env: { ...process.env, VITE_API_URL: `http://127.0.0.1:${apiPort}` }, stdio: 'ignore' });
  const origin = `http://127.0.0.1:${port}`;
  await waitFor(async () => (await fetch(origin)).ok, 'Vite');
  firefox = spawn(process.env.FIREFOX_BIN || 'firefox', ['--headless', '--no-remote', '--profile', profile, '--remote-debugging-port', String(debug)], { stdio: 'ignore' });
  await waitFor(async () => { await fetch(`http://127.0.0.1:${debug}/`); return true; }, 'Firefox');
  ws = new WebSocket(`ws://127.0.0.1:${debug}/session`);
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  let sequence = 0;
  const pending = new Map();
  ws.addEventListener('message', ({ data }) => {
    const body = JSON.parse(data), item = pending.get(body.id);
    if (item) { clearTimeout(item.timer); pending.delete(body.id); body.type === 'error' ? item.reject(new Error(`${body.error}: ${body.message}`)) : item.resolve(body.result); }
  });
  function command(method, params = {}) {
    const id = ++sequence;
    return new Promise((resolve, reject) => { const timer = setTimeout(() => { pending.delete(id); reject(new Error(method)); }, 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })); });
  }
  await command('session.new', { capabilities: { alwaysMatch: {} } });
  const { context } = await command('browsingContext.create', { type: 'tab' });
  async function evaluate(expression) {
    const result = await command('script.evaluate', { expression, target: { context }, awaitPromise: true });
    if (result.type === 'exception') throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }
  const click = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const waitText = (text) => waitFor(() => evaluate(`document.body.textContent.includes(${JSON.stringify(text)})`), text);
  async function screenshot(name) {
    if (!process.env.COMANDAS_SCREENSHOT_DIR) return;
    const result = await command('browsingContext.captureScreenshot', { context });
    await writeFile(join(process.env.COMANDAS_SCREENSHOT_DIR, `${name}.png`), Buffer.from(result.data, 'base64'));
  }
  await command('browsingContext.navigate', { context, url: `${origin}/login`, wait: 'complete' });
  await evaluate(`localStorage.setItem('token','jwt-ficticio'); localStorage.setItem('relaxabarber:filial:${own}',${JSON.stringify(a)})`);
  await command('browsingContext.setViewport', { context, viewport: { width: 1440, height: 1100 } });
  await command('browsingContext.navigate', { context, url: `${origin}/comandas`, wait: 'complete' });
  await waitText('Cliente fictício 1');
  assert.equal(await evaluate('document.querySelectorAll(".comanda-card").length'), 6);
  assert.ok(await evaluate('document.querySelector(".comandas-indicadores").textContent.includes("222,00")'));
  await screenshot('comandas-desktop');
  await click('.comandas-paginacao button:last-child'); await waitText('Página 2 de 2');
  assert.equal(await evaluate('document.querySelectorAll(".comanda-card").length'), 2);
  assert.ok(requests.some((r) => r.params.pagina === '2' && r.params.filial_id === a));
  await click('.comandas-paginacao button:first-child'); await waitText('Página 1 de 2');
  await evaluate('document.querySelector(".comanda-card footer button").focus(); document.activeElement.click()');
  await waitText('Identificadores completos');
  assert.ok(await evaluate('document.querySelector("dialog").open && !!document.activeElement.closest("dialog")'));
  for (let tab = 0; tab < 3; tab++) {
    await command('input.performActions', { context, actions: [{ type: 'key', id: 'tabs', actions: [{ type: 'keyDown', value: '\uE004' }, { type: 'keyUp', value: '\uE004' }] }] });
    assert.ok(await evaluate('!!document.activeElement.closest("dialog")'));
  }
  await command('input.performActions', { context, actions: [{ type: 'key', id: 'keyboard', actions: [{ type: 'keyDown', value: '\uE00C' }, { type: 'keyUp', value: '\uE00C' }] }] });
  await waitFor(() => evaluate('!document.querySelector("dialog")'), 'Escape');
  assert.ok(await evaluate('document.activeElement.matches(".comanda-card footer button")'));
  for (const code of [404, 503]) {
    detailMode = code; await click('.comanda-card footer button');
    await waitText(code === 404 ? 'Comanda não encontrada' : 'Indisponível');
    await click('dialog header button');
  }
  const revalidacoes = requests.filter((r) => r.path === '/filiais').length;
  detailMode = 403; await click('.comanda-card footer button');
  await waitFor(() => requests.filter((r) => r.path === '/filiais').length > revalidacoes, '403 revalida acesso');
  await waitFor(() => evaluate('!document.querySelector("dialog")'), '403 descarta detalhe');
  detailMode = 200; await waitText('Cliente fictício 1');
  await click('.comandas-abas button:nth-child(3)');
  await waitFor(() => evaluate('document.querySelectorAll(".comanda-card").length === 4'), 'aba abertas');
  await click('.comandas-abas button:first-child'); await waitText('Página 1 de 2');
  async function search(value) {
    await evaluate(`(()=>{const campo=document.querySelector('input[type="search"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(campo,${JSON.stringify(value)}); campo.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    await click('.comandas-filtros button[type=submit]');
  }
  await search('fictício 8');
  await waitFor(() => evaluate('document.querySelectorAll(".comanda-card").length === 1'), 'pesquisa');
  assert.ok(requests.some((r) => r.params.busca === 'fictício 8'));
  await search(''); await waitText('Página 1 de 2');
  await command('browsingContext.setViewport', { context, viewport: { width: 900, height: 1000 } });
  assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'));
  await screenshot('comandas-tablet');
  await command('browsingContext.setViewport', { context, viewport: { width: 390, height: 844 } });
  assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth'));
  assert.ok(await evaluate('document.querySelector("button[title=Sair]").getBoundingClientRect().width > 0'));
  await screenshot('comandas-mobile');
  await click('[aria-label="Visualizar em lista"]');
  assert.ok(await evaluate('!!document.querySelector(".comandas-lista")'));
  panelMode = 'delay'; await click('.comandas-cabecalho button'); await waitText('Carregando comandas'); await waitText('Cliente fictício 1');
  panelMode = 'error'; await click('.comandas-cabecalho button'); await waitText('Consulta temporariamente indisponível');
  panelMode = 'empty'; await click('.comandas-estado button'); await waitText('Nenhuma comanda encontrada');
  panelMode = 'normal';
  await evaluate(`(()=>{const select=document.querySelector('[aria-label="Filial ativa"]');select.value=${JSON.stringify(b)};select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await waitFor(() => requests.some((r) => r.path === '/comandas/painel' && r.params.filial_id === b), 'filial B'); await waitText('Nenhuma comanda encontrada');
  role = 'barbeiro';
  await evaluate(`localStorage.setItem('relaxabarber:filial:${own}',${JSON.stringify(a)})`);
  await command('browsingContext.navigate', { context, url: `${origin}/comandas`, wait: 'complete' }); await waitText('Cliente fictício 1');
  assert.equal(await evaluate('document.querySelectorAll(".comanda-card").length'), 4);
  assert.equal(await evaluate('document.querySelector(".comandas-filtros select").options.length'), 2);
  console.log('PASS: cards, indicadores, paginação, detalhe, Escape/foco, erros, busca, status, grade/lista, loading, vazio, filial, perfil e mobile; API fictícia local.');
  await command('session.end');
} finally {
  ws?.close(); vite?.kill('SIGTERM'); firefox?.kill('SIGTERM');
  server.closeAllConnections(); await new Promise((resolve) => server.close(resolve));
  await new Promise((resolve) => setTimeout(resolve, 300));
  await rm(profile, { recursive: true, force: true });
}
