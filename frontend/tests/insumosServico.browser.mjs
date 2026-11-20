/** Firefox com API simulada em portas locais efêmeras. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'rb-insumos-'));
const filial = '10000000-0000-4000-8000-000000000001';
const servico = '20000000-0000-4000-8000-000000000001';
const creme = { id: 'creme', nome: 'Creme', unidade: 'ml', ativo: true, consumo: true };
const chamadas = [];
let receita = [];
let cadastro, escritas = 0;
const fisico = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin || '*');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization, Idempotency-Key');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS');
  if (req.method === 'OPTIONS') return res.writeHead(204).end();
  const url = new URL(req.url, 'http://local');
  const reply = data => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(data)); };
  if (url.pathname === '/auth/me') return reply({ id: 'admin', nome: 'ADMIN QA', email: 'qa@example.com', perfil: 'admin', ativo: true });
  if (url.pathname === '/filiais') return reply([{ id: filial, nome: 'QA', fuso_horario: 'America/Recife' }]);
  if (url.pathname === '/estoque/produtos') return reply([creme, { ...creme, id: 'revenda', nome: 'Revenda', consumo: false }]);
  if (url.pathname.startsWith('/servicos/cadastros/')) {
    if (cadastro?.chave === url.pathname.split('/').at(-1)) return reply(cadastro.dados);
    return res.writeHead(404).end();
  }
  if ((url.pathname === '/servicos/' && req.method === 'POST') || (url.pathname === '/servicos/' + servico && req.method === 'PUT')) {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const dados = { ...JSON.parse(raw), id: servico };
    if (req.method === 'POST') assert.ok(req.headers['idempotency-key']);
    cadastro = { chave: req.headers['idempotency-key'], dados };
    escritas++;
    res.statusCode = 504; return reply({});
  }
  if (url.pathname === '/servicos/' + servico) return reply(cadastro?.dados ?? {});
  if (url.pathname === '/servicos/' + servico + '/insumos') {
    if (req.method === 'PUT') {
      let body = ''; for await (const chunk of req) body += chunk;
      receita = JSON.parse(body);
      chamadas.push({ filial: url.searchParams.get('filial_id'), receita });
      if (chamadas.length === 1) { res.statusCode = 504; return reply({}); }
    }
    return reply(receita);
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
  const ir = path => comando('browsingContext.navigate', { context, url: origem + path, wait: 'interactive' });
  async function avaliar(expression) {
    const r = await comando('script.evaluate', { expression, target: { context }, awaitPromise: true });
    if (r.type === 'exception') throw Error(r.exceptionDetails.text);
    return r.result.value;
  }
  const form = 'form[aria-label="Insumos do serviço"]';
  const buscar = seletor => `document.querySelector(${JSON.stringify(form + ' ' + seletor)})`;
  const botao = texto => `[...document.querySelectorAll(${JSON.stringify(form + ' button')})].find(e=>e.textContent===${JSON.stringify(texto)})`;
  await comando('browsingContext.navigate', { context, url: origem + '/login', wait: 'none' });
  await espera(() => avaliar(`location.origin === ${JSON.stringify(origem)} && document.readyState !== 'loading'`), 'login');
  await avaliar("localStorage.setItem('token','ficticio')");
  await ir('/servicos/novo');
  const campo = (seletor, valor) => avaliar(`(()=>{const e=document.querySelector(${JSON.stringify('.servico-form ' + seletor)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(valor)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  const mensagem = async texto => {
    try { await espera(() => avaliar(`document.body.textContent.includes(${JSON.stringify(texto)})`), texto); }
    catch (erro) { throw new Error(`${erro.message}. ${await avaliar("location.pathname + ' ' + (document.querySelector('main')?.innerText ?? document.body.innerText)")}`); }
  };
  const acao = texto => avaliar(`[...document.querySelectorAll('.servico-form button')].find(b=>b.textContent===${JSON.stringify(texto)}).click()`);
  await mensagem('Novo serviço');
  await campo('input[placeholder="Ex: Corte de cabelo"]', 'Corte');
  await campo('input[placeholder="Ex: 30"]', '30');
  await acao('Salvar e configurar insumos'); await mensagem('Resultado não confirmado.');
  assert.ok(await avaliar('document.querySelector(".servico-form button[type=submit]").disabled'));
  await acao('Conferir resultado'); await mensagem('Serviço cadastrado com sucesso.');
  await campo('input[placeholder="Ex: Corte de cabelo"]', 'Corte atualizado');
  await acao('Salvar'); await mensagem('Resultado não confirmado.');
  await acao('Conferir resultado'); await mensagem('Serviço atualizado com sucesso.');
  assert.equal(escritas, 2);
  await espera(() => avaliar('!!' + buscar('option[value=creme]')), 'opções de uso interno');
  assert.equal(await avaliar('!!' + buscar('option[value=revenda]')), false);
  await avaliar(`(()=>{const e=${buscar('select')};e.value='creme';e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await avaliar(`${botao('Adicionar insumo')}.click()`);
  await espera(() => avaliar('!!' + buscar('input[type=number]')), 'quantidade');
  await avaliar(`(()=>{const e=${buscar('input[type=number]')};Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'1.257');e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await avaliar(`${botao('Salvar insumos')}.click()`);
  await mensagem('Resultado incerto. Compare com os insumos');
  assert.equal(await avaliar(buscar('input[type=number]') + '.value'), '1.257');
  await avaliar(`${botao('Conferir insumos')}.click()`);
  await mensagem('Os insumos registrados correspondem');
  assert.deepEqual(chamadas[0], { filial, receita: [{ produto_id: 'creme', quantidade: '1.257' }] });
  await avaliar(`${botao('Remover')}.click()`);
  await espera(() => avaliar('!' + buscar('input[type=number]')), 'remoção na interface');
  await avaliar(`${botao('Salvar insumos')}.click()`);
  await espera(() => Promise.resolve(chamadas.length === 2), 'remoção');
  assert.deepEqual(chamadas[1], { filial, receita: [] });
  await comando('session.end');
  console.log('PASS Firefox: cadastro e remoção de insumos na filial selecionada.');
} finally {
  ws?.close(); vite?.kill(); firefox?.kill(); fisico.closeAllConnections();
  await new Promise(r => fisico.close(r));
  await rm(profile, { recursive: true, force: true, maxRetries: 12, retryDelay: 250 });
}
