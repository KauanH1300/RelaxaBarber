/** Chrome real + API fictícia. Nenhum acesso ao Supabase.
 * Servir Vite em 127.0.0.1:15173 com VITE_API_URL=http://127.0.0.1:18081.
 * Executar com Node 22+ e Chrome instalado: node tests/clientes.browser.mjs.
 */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const origin = 'http://127.0.0.1:15173';
const a = '10000000-0000-4000-8000-000000000001', b = '10000000-0000-4000-8000-000000000002';
const uid = '20000000-0000-4000-8000-000000000001';
const clienteId = '30000000-0000-4000-8000-000000000001';
const clientes = [{ id: clienteId, nome: 'Ana de teste', telefone: '81999999999', email: 'ana@example.test', ativo: true, conta_ativada: false, data_cadastro: '2026-11-01T12:00:00Z' }];
let role = 'admin', writeStatus = 200, listStatus = 200, detailStatus = 200, delay = 0;
const requests = [], checks = [];
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', origin);
  res.setHeader('Access-Control-Allow-Headers', 'Authorization,Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PATCH,OPTIONS');
  if (req.method === 'OPTIONS') return res.writeHead(204).end();
  const url = new URL(req.url, origin);
  requests.push({ method: req.method, path: url.pathname, params: Object.fromEntries(url.searchParams) });
  const send = (status, data) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
  if (url.pathname === '/auth/me') return send(200, { id: uid, nome: 'Operador QA', email: 'qa@example.test', perfil: role, ativo: true });
  if (url.pathname === '/filiais') return send(200, [{ id: a, nome: 'Unidade QA A', fuso_horario: 'America/Recife' }, { id: b, nome: 'Unidade QA B', fuso_horario: 'America/Recife' }]);
  if (/\/resumo(-financeiro)?$/.test(url.pathname)) return send(200, { cliente_id: clienteId, escopo_filiais: role === 'admin' ? 'empresa' : 'filiais_autorizadas', escopo_profissional: 'todos', parcial: role !== 'admin', atendimentos_concluidos: 0, filiais: [], financeiro_disponivel: false, total_gasto: null });
  if (url.pathname === '/clientes' && req.method === 'GET') {
    const status = listStatus;
    if (status === 401 || status === 403) listStatus = 200;
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
    if (status !== 200) return send(status, { detail: `Falha simulada ${status}` });
    const busca = (url.searchParams.get('busca') || '').toLocaleLowerCase();
    return send(200, url.searchParams.get('filial_id') === b ? [] : clientes.filter((c) => `${c.nome} ${c.telefone}`.toLocaleLowerCase().includes(busca)));
  }
  if (url.pathname.startsWith('/clientes/') && req.method === 'GET') {
    return send(detailStatus, detailStatus === 200 ? clientes.find((c) => c.id === url.pathname.split('/').at(-1)) : { detail: `Falha simulada ${detailStatus}` });
  }
  if (url.pathname.startsWith('/clientes') && ['POST', 'PATCH'].includes(req.method)) {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw);
    if (writeStatus !== 200) return send(writeStatus, { detail: writeStatus === 409 ? 'DADO PRIVADO DE OUTRA FILIAL' : [{ msg: `Validação simulada ${writeStatus}` }] });
    assert.equal(url.searchParams.get('filial_id'), a);
    if (req.method === 'POST') {
      assert.equal(body.filial_id, a);
      const novo = { ...clientes[0], id: '30000000-0000-4000-8000-000000000002', ...body };
      clientes.push(novo); return send(201, novo);
    }
    const cliente = clientes.find((c) => c.id === url.pathname.split('/').at(-1));
    assert.deepEqual(Object.keys(body).sort(), ['email', 'nome', 'telefone']);
    Object.assign(cliente, body); return send(200, cliente);
  }
  return send(404, {});
});
const qaDir = await mkdtemp(join(tmpdir(), 'rb-clientes-browser-'));
const profile = join(qaDir, 'profile'); await mkdir(profile);
const portServer = createServer();
await new Promise((resolve) => portServer.listen(0, '127.0.0.1', resolve));
const debug = portServer.address().port; await new Promise((resolve) => portServer.close(resolve));
let chrome, ws;
async function waitFor(fn, label) {
  const end = Date.now() + 15000;
  while (Date.now() < end) { try { if (await fn()) return; } catch { /* aguarda renderização */ } await new Promise((resolve) => setTimeout(resolve, 100)); }
  throw new Error(`Tempo excedido: ${label}`);
}
try {
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(18081, '127.0.0.1', resolve); });
  await waitFor(async () => (await fetch(origin)).ok, 'Vite');
  chrome = spawn(process.env.CHROME_BIN || (process.platform === 'win32' ? 'C:/Program Files/Google/Chrome/Application/chrome.exe' : 'google-chrome'), ['--headless=new', '--no-first-run', '--disable-background-networking', `--remote-debugging-port=${debug}`, `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore', windowsHide: true });
  let tabs;
  await waitFor(async () => { tabs = await (await fetch(`http://127.0.0.1:${debug}/json/list`)).json(); return tabs.some((t) => t.type === 'page'); }, 'Chrome');
  ws = new WebSocket(tabs.find((t) => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let sequence = 0; const pending = new Map();
  function command(method, params = {}) {
    return new Promise((resolve, reject) => { const id = ++sequence; const timer = setTimeout(() => { pending.delete(id); reject(new Error(method)); }, 15000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })); });
  }
  ws.onmessage = ({ data }) => {
    const body = JSON.parse(data);
    if (body.method === 'Page.javascriptDialogOpening') { void command('Page.handleJavaScriptDialog', { accept: true }); return; }
    const p = pending.get(body.id);
    if (p) { clearTimeout(p.timer); pending.delete(body.id); body.error ? p.reject(new Error(body.error.message)) : p.resolve(body.result); }
  };
  async function evaluate(expression) {
    const result = await command('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  }
  const text = (value) => waitFor(() => evaluate(`document.body.textContent.includes(${JSON.stringify(value)})`), value);
  const click = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const button = (label) => evaluate(`Array.from(document.querySelectorAll('button')).find(b=>b.textContent===${JSON.stringify(label)}).click()`);
  const input = (selector, value) => evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await command('Page.enable');
  await command('Page.navigate', { url: `${origin}/login` });
  await waitFor(() => evaluate('!!document.querySelector("input")'), 'login');
  await evaluate(`localStorage.setItem('token','jwt-ficticio');localStorage.setItem('relaxabarber:filial:${uid}','${a}')`);
  async function load() { await command('Page.navigate', { url: `${origin}/clientes` }); await text('Ana de teste'); }
  delay = 800; await command('Page.navigate', { url: `${origin}/clientes` }); await text('Carregando clientes...'); await text('Ana de teste'); delay = 0;
  checks.push('carregamento e lista da filial');
  await input('#busca-clientes', '  ninguém  '); await click('.clientes-busca button[type=submit]'); await text('Nenhum cliente encontrado');
  assert.ok(requests.some((r) => r.params.busca === 'ninguém' && r.params.filial_id === a));
  await button('Limpar busca'); await text('Ana de teste'); checks.push('busca no servidor, vazio filtrado e limpar');
  await click('[aria-label="Ver cadastro de Ana de teste"]'); await text('ana@example.test');
  assert.equal(await evaluate('document.querySelector(".cliente-detalhe input")===null'), true);
  assert.equal(await evaluate('document.activeElement.textContent'), 'Dados cadastrais');
  await button('Fechar perfil'); checks.push('consulta em leitura e foco');
  await button('Novo cliente'); await input('[name=nome]', 'Rascunho QA'); await input('[name=telefone]', '81988887777');
  await evaluate('window.confirm=()=>false'); await button('Cancelar'); assert.ok(await evaluate('!!document.querySelector(".cliente-form")'));
  await click('a[href="/perfil"]'); assert.equal(await evaluate('location.pathname'), '/clientes');
  async function trocar(id) { await evaluate(`(()=>{const e=document.querySelector('[aria-label="Filial ativa"]');e.value='${id}';e.dispatchEvent(new Event('change',{bubbles:true}));})()`); }
  await trocar(b); assert.equal(await evaluate('document.querySelector("[name=nome]").value'), 'Rascunho QA');
  await evaluate('window.confirm=()=>true'); await trocar(b); await text('Nenhum cliente vinculado'); await button('Novo cliente');
  assert.equal(await evaluate('document.querySelector("[name=nome]").value'), ''); await button('Cancelar');
  await trocar(a); await text('Ana de teste'); await button('Novo cliente'); await text('Rascunho recuperado');
  assert.equal(await evaluate('document.querySelector("[name=nome]").value'), 'Rascunho QA');
  await click('a[href="/perfil"]'); await waitFor(() => evaluate('location.pathname==="/perfil"'), 'perfil');
  await click('a[href="/clientes"]'); await text('Ana de teste'); await button('Novo cliente'); await text('Rascunho recuperado');
  await evaluate('history.back()'); await waitFor(() => evaluate('location.pathname==="/perfil"'), 'voltar');
  await evaluate('history.forward()'); await text('Ana de teste'); await button('Novo cliente'); await text('Rascunho recuperado');
  await command('Page.reload');
  await waitFor(() => evaluate('!!document.querySelector(".clientes-lista li") && !document.querySelector(".cliente-form")'), 'recarregar página');
  await button('Novo cliente'); await text('Rascunho recuperado');
  assert.equal(await evaluate('document.querySelector("[name=nome]").value'), 'Rascunho QA');
  checks.push('cancelar/navegar/trocar de filial e rascunhos isolados');
  checks.push('rascunho preservado ao voltar, avançar e recarregar');
  writeStatus = 409; await button('Salvar cliente'); await text('Já existe um cadastro');
  assert.equal(await evaluate('document.body.textContent.includes("DADO PRIVADO")'), false);
  assert.equal(await evaluate('document.querySelector("[name=nome]").value'), 'Rascunho QA');
  writeStatus = 422; await button('Salvar cliente'); await text('Validação simulada 422');
  checks.push('409 seguro e 422 mantêm formulário');
  writeStatus = 503; await button('Salvar cliente'); await text('Há um salvamento a conferir');
  await button('Fechar e conferir lista'); await text('Ana de teste'); await button('Novo cliente'); await text('Há um salvamento a conferir');
  assert.ok(await evaluate('document.querySelector(".cliente-form button[type=submit]").disabled'));
  await button('Descartar rascunho após conferência'); await text('Ana de teste');
  checks.push('escrita incerta persiste bloqueio após reabrir');
  writeStatus = 200; await button('Novo cliente'); await input('[name=nome]', 'Novo QA'); await input('[name=telefone]', '81977776666');
  await button('Salvar cliente'); await text('Cliente cadastrado com sucesso.'); await text('Novo QA');
  await click('[aria-label="Editar Ana de teste"]'); await waitFor(() => evaluate('document.querySelector("[name=nome]")?.value==="Ana de teste"'), 'carregamento edição');
  assert.equal(await evaluate('document.querySelector(".cliente-form button[type=submit]").disabled'), true);
  await input('[name=email]', ''); await button('Salvar cliente'); await text('Cliente atualizado com sucesso.');
  assert.equal(clientes[0].email, null); checks.push('criar, editar, remover e-mail e atualizar lista');
  detailStatus = 404; await click('[aria-label="Ver cadastro de Ana de teste"]'); await text('Falha simulada 404'); detailStatus = 200;
  await button('Tentar consultar novamente'); await text('Não informado'); checks.push('erro de consulta e nova tentativa');
  for (const [width, height] of [[1440, 1000], [900, 1000], [390, 844]]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));
    const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
    await writeFile(join(qaDir, `clientes-${width}.png`), Buffer.from(shot.data, 'base64'));
  }
  checks.push('responsividade 1440/900/390');
  listStatus = 503; await button('Atualizar clientes'); await text('Falha simulada 503'); listStatus = 200;
  await button('Tentar novamente'); await text('Ana de teste'); checks.push('erro de listagem e nova tentativa');
  const antes403 = requests.filter((r) => r.path === '/filiais').length;
  listStatus = 403; await button('Atualizar clientes');
  await waitFor(() => requests.filter((r) => r.path === '/filiais').length > antes403, '403 revalida filiais');
  await text('Ana de teste'); assert.equal(await evaluate('localStorage.getItem("token")'), 'jwt-ficticio');
  checks.push('403 revalida acesso sem encerrar a sessão');
  for (const perfil of ['recepcao', 'barbeiro_chefe', 'barbeiro']) { role = perfil; await load(); await button('Novo cliente'); assert.ok(await evaluate('!document.querySelector(".cliente-form fieldset").disabled')); await button('Cancelar'); }
  checks.push('perfis autorizados mantêm cadastro e edição');
  role = 'invalido'; await load(); assert.ok(await evaluate('!Array.from(document.querySelectorAll("button")).some(b=>b.textContent==="Novo cliente")')); checks.push('perfil desconhecido não oferece escrita');
  role = 'admin'; listStatus = 401; await command('Page.navigate', { url: `${origin}/clientes` });
  await waitFor(() => evaluate('location.pathname==="/login"'), '401'); assert.equal(await evaluate('localStorage.getItem("token")'), null); checks.push('401 encerra sessão');
  console.log(JSON.stringify({ browser: 'Chrome real', api: 'fictícia local', checks, screenshots: [1440, 900, 390].map((w) => join(qaDir, `clientes-${w}.png`)) }));
} catch (error) { console.error(JSON.stringify({ error: error.message, passed: checks })); process.exitCode = 1; }
finally {
  if (ws?.readyState === 1) { ws.send(JSON.stringify({ id: 999999, method: 'Browser.close' })); await new Promise((resolve) => setTimeout(resolve, 300)); ws.close(); }
  chrome?.kill(); server.closeAllConnections(); await new Promise((resolve) => server.close(resolve));
}
