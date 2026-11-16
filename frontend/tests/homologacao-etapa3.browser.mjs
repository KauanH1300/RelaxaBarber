/** Opt-in: React + FastAPI reais, exclusivamente no namespace PostgreSQL sem rede. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer, request } from 'node:http';
import { readFile, writeFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

assert.equal(process.env.RB_HOMOLOG_ISOLADO, 'descartavel-sem-rede');
const seed = JSON.parse(await readFile('/tmp/homolog-seed.json', 'utf8'));
const evidence = { ambiente: 'Docker network none; PostgreSQL tmpfs; FastAPI real; Firefox real', verificacoes: [] };
async function record(cenario, dados = {}) {
  evidence.verificacoes.push({ cenario, ...dados });
  await writeFile('/evidencias/homologacao.json', JSON.stringify(evidence, null, 2));
  console.log('PASS', cenario, JSON.stringify(dados));
}
const calls = []; let delayNext = false, failNext = false;
// Proxy transparente: todas as respostas de negócio vêm do FastAPI real.
// Somente falhas de transporte são injetadas, sem substituir dados financeiros.
const proxy = createServer((req, res) => {
  const chunks = [];
  req.on('data', (c) => chunks.push(c));
  req.on('end', () => {
    const raw = Buffer.concat(chunks);
    const payment = req.method === 'POST' && req.url.includes('/fechamento-financeiro');
    const delayed = payment && delayNext; if (delayed) delayNext = false;
    if (payment) calls.push({ path: req.url, key: req.headers['idempotency-key'], raw: raw.toString() });
    if (payment && failNext) {
      failNext = false;
      res.writeHead(503, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': 'http://127.0.0.1:5173' });
      res.end(JSON.stringify({ detail: { codigo: 'confirmacao_indeterminada' } })); return;
    }
    const upstream = request({ hostname: '127.0.0.1', port: 8001, path: req.url, method: req.method, headers: req.headers }, (response) => {
      const data = []; response.on('data', (c) => data.push(c));
      response.on('end', () => {
        const send = () => { if (!res.destroyed) { res.writeHead(response.statusCode, response.headers); res.end(Buffer.concat(data)); } };
        if (delayed) setTimeout(send, 17000); else send();
      });
    });
    upstream.on('error', (e) => { console.log('PROXY_ERROR', e.code); res.writeHead(502); res.end(); }); upstream.end(raw);
  });
});
await new Promise((resolve) => proxy.listen(8000, '127.0.0.1', resolve));
const api = 'http://127.0.0.1:8001';
async function login(perfil) {
  const r = await fetch(`${api}/auth/login`, { method: 'POST', body: new URLSearchParams({ username: `${perfil}@homolog.example.com`, password: 'Somente-local-123!' }) });
  assert.equal(r.status, 200); return (await r.json()).access_token;
}
const tokens = Object.fromEntries(await Promise.all(Object.keys(seed.usuarios).map(async (p) => [p, await login(p)])));
async function http(path, { method = 'GET', body, perfil = 'admin', key } = {}) {
  const r = await fetch(api + path, { method, headers: { Authorization: `Bearer ${tokens[perfil]}`, 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  return { status: r.status, body: await r.json() };
}
const scoped = (id, suffix = '') => `/comandas/${id}${suffix}?filial_id=${seed.filial}`;
const receipt = (valor, forma = 'pix') => ({ valor, forma, recebido_em: new Date(Date.now() - 60000).toISOString(), confirmado: true });
let day = 0;
async function appointment(perfil = 'barbeiro') {
  const date = `2099-02-${String(++day).padStart(2, '0')}`;
  const r = await http('/agendamentos', { method: 'POST', body: { filial_id: seed.filial, cliente_id: seed.cliente, barbeiro_id: seed.usuarios[perfil], data: date, hora_inicio: '09:00', servicos: [{ servico_id: seed.servico }] } });
  assert.equal(r.status, 201, JSON.stringify(r));
  for (const status of ['aguardando', 'em_atendimento', 'concluido']) {
    const transition = await http(`/agendamentos/${r.body.id}/status?filial_id=${seed.filial}`, { method: 'PATCH', body: { status } });
    assert.equal(transition.status, 200, JSON.stringify(transition));
  }
  const panel = await http(`/comandas/painel?filial_id=${seed.filial}&data_inicio=${date}&data_fim=${date}`);
  assert.equal(panel.status, 200, JSON.stringify(panel));
  const c = panel.body.itens[0]; assert.ok(c); assert.equal(c.status, 'aberta'); assert.equal(c.data_fechamento, null); assert.equal(c.atendimento.status, 'concluido');
  const financial = await http(scoped(c.id, '/financeiro'));
  assert.equal(financial.body.recebido_liquido, '0.00');
  await record('criar/iniciar/concluir via HTTP real preserva comanda aberta', { id: c.id, perfil, date });
  return { id: c.id, date };
}
async function financial(id) { const r = await http(scoped(id, '/financeiro')); assert.equal(r.status, 200); return r.body; }

const profile = await mkdtemp(join(tmpdir(), 'rb-homolog-firefox-'));
let vite, firefox, ws, debugPage;
async function waitFor(check, label) {
  const end = Date.now() + 45000;
  while (Date.now() < end) { try { if (await check()) return; } catch { /* polling read only */ } await new Promise((r) => setTimeout(r, 120)); }
  throw new Error(`Timeout: ${label}`);
}
try {
  vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5173', '--strictPort'], { cwd: '/app', env: { ...process.env, VITE_API_URL: 'http://127.0.0.1:8000' }, stdio: 'inherit' });
  await waitFor(async () => (await fetch('http://127.0.0.1:5173')).ok, 'Vite');
  firefox = spawn('firefox', ['--headless', '--no-remote', '--profile', profile, '--remote-debugging-port', '9222'], { stdio: 'ignore' });
  await waitFor(async () => { await fetch('http://127.0.0.1:9222'); return true; }, 'Firefox');
  ws = new WebSocket('ws://127.0.0.1:9222/session');
  await new Promise((resolve, reject) => { ws.addEventListener('open', resolve, { once: true }); ws.addEventListener('error', reject, { once: true }); });
  let sequence = 0; const pending = new Map();
  ws.addEventListener('message', ({ data }) => { const b = JSON.parse(data), p = pending.get(b.id); if (p) { clearTimeout(p.timer); pending.delete(b.id); b.type === 'error' ? p.reject(new Error(b.message)) : p.resolve(b.result); } });
  function command(method, params = {}) { const id = ++sequence; return new Promise((resolve, reject) => { const timer = setTimeout(() => reject(new Error(method)), 45000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })); }); }
  await command('session.new', { capabilities: { alwaysMatch: {} } });
  const { context } = await command('browsingContext.create', { type: 'tab' });
  async function evaluate(expression) { const r = await command('script.evaluate', { expression, target: { context }, awaitPromise: true }); if (r.type === 'exception') throw new Error(r.exceptionDetails.text); return r.result.type === 'null' ? null : r.result.value; }
  debugPage = async () => { await writeFile('/evidencias/ultima-pagina.txt', await evaluate('document.body.innerText')); const s = await command('browsingContext.captureScreenshot', { context }); await writeFile('/evidencias/ultima-pagina.png', Buffer.from(s.data, 'base64')); };
  const click = (s) => evaluate(`document.querySelector(${JSON.stringify(s)}).click()`);
  const waitText = (t) => waitFor(() => evaluate(`document.querySelector('dialog')?.textContent.includes(${JSON.stringify(t)})`), t);
  async function fill(s, value) { await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(s)});Object.getOwnPropertyDescriptor(e instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e instanceof HTMLSelectElement?'change':'input',{bubbles:true}));})()`); }
  const form = 'form[data-operacao="fechamento-financeiro"]';
  async function open(c, perfil = 'admin') {
    await command('browsingContext.navigate', { context, url: 'http://127.0.0.1:5173/login', wait: 'complete' });
    await evaluate(`localStorage.setItem('token',${JSON.stringify(tokens[perfil])});localStorage.setItem(${JSON.stringify(`relaxabarber:filial:${seed.usuarios[perfil]}`)},${JSON.stringify(seed.filial)})`);
    await command('browsingContext.navigate', { context, url: 'http://127.0.0.1:5173/comandas', wait: 'complete' });
    await waitFor(() => evaluate('!!document.querySelector(".comandas-filtros")'), 'painel real');
    await fill('input[aria-label="Data final do atendimento"]', c.date);
    await fill('input[aria-label="Data inicial do atendimento"]', c.date);
    await click('.comandas-filtros button[type="submit"]');
    await waitFor(() => evaluate('!!document.querySelector(".comanda-card footer button")'), 'card real');
    await click('.comanda-card footer button'); await waitText('Histórico financeiro');
    await waitFor(() => evaluate('document.querySelector(".comanda-financeiro")?.getAttribute("aria-busy")==="false"'), 'financeiro real');
  }
  async function parcel(i, value, forma = 'pix') { const s = `${form} .financeiro-parcela:nth-of-type(${i})`; await fill(`${s} input[inputmode="decimal"]`, value); await fill(`${s} select`, forma); await click(`${s} input[type="checkbox"]`); }
  async function review() { await click(`${form} button[type="submit"]`); await waitText('Confirmar:'); }
  async function confirm() { await evaluate('document.querySelector(".financeiro-confirmacao button").click();document.querySelector(".financeiro-confirmacao button")?.click()'); }
  async function closed(c) {
    await waitText('Situação financeira: Fechada');
    await waitFor(() => evaluate('document.querySelector(".financeiro-situacao")?.textContent==="Situação financeira: Fechada"'), 'detalhe atualizado');
    await waitFor(() => evaluate('document.querySelector(".comandas-indicadores article strong")?.textContent==="0"'), 'indicador atualizado');
    const f = await financial(c.id); assert.equal(f.situacao, 'fechado'); assert.equal(f.saldo, '0.00'); return f;
  }

  const c = await appointment();
  await open(c); await parcel(1, '100.00');
  const before = calls.length;
  await click(`${form} button[type="submit"]`); await waitText('exatamente igual'); assert.equal(calls.length, before);
  const rejected = await http(scoped(c.id, '/fechamento-financeiro'), { method: 'POST', key: randomUUID(), body: { pagamentos: [receipt('100.00')] } });
  assert.equal(rejected.status, 409); let f = await financial(c.id); assert.equal(f.historico.pagamentos.length, 0); assert.equal(f.situacao, 'aberto');
  await record('insuficiente bloqueado na UI e rejeitado no FastAPI sem persistência', { status: rejected.status });
  await click(`${form} fieldset>button[type="button"]`); await parcel(2, '200.00', 'dinheiro'); await review(); await confirm();
  f = await closed(c); assert.equal(f.historico.pagamentos.length, 2); assert.equal(f.recebido_liquido, '300.00'); assert.equal(calls.length, before + 1);
  const original = calls.at(-1);
  const replay = await http(scoped(c.id, '/fechamento-financeiro'), { method: 'POST', key: original.key, body: JSON.parse(original.raw) });
  assert.equal(replay.status, 200); assert.equal((await financial(c.id)).historico.pagamentos.length, 2);
  await record('PIX100 + dinheiro200, clique duplo, replay, detalhes e indicadores automáticos', { id: c.id, pagamentos: f.historico.pagamentos.map((p) => ({ valor: p.valor, forma: p.forma })), replay: replay.status });
  const shot = await command('browsingContext.captureScreenshot', { context }); await writeFile('/evidencias/fechamento-combinado.png', Buffer.from(shot.data, 'base64'));

  for (const perfil of ['recepcao', 'barbeiro', 'barbeiro_chefe']) {
    const own = await appointment(perfil === 'recepcao' ? 'barbeiro' : perfil);
    await open(own, perfil); await parcel(1, '300.00', perfil === 'recepcao' ? 'credito' : 'debito'); await review(); await confirm();
    assert.equal((await closed(own)).historico.pagamentos.length, 1);
    const wrongBranch = await http(`/comandas/${own.id}/financeiro?filial_id=${seed.outra_filial}`, { perfil }); assert.ok([403, 404].includes(wrongBranch.status));
    await record(`UI e fechamento real ${perfil}; outra filial negada`, { status_filial: wrongBranch.status });
  }
  for (const perfil of ['barbeiro', 'barbeiro_chefe']) {
    const other = await appointment(perfil === 'barbeiro' ? 'barbeiro_chefe' : 'barbeiro');
    const r = await http(scoped(other.id, '/financeiro'), { perfil }); assert.equal(r.status, 404);
    const w = await http(scoped(other.id, '/fechamento-financeiro'), { perfil, method: 'POST', key: randomUUID(), body: { pagamentos: [receipt('300.00')] } }); assert.equal(w.status, 404);
    assert.equal((await financial(other.id)).historico.pagamentos.length, 0);
    await record(`${perfil} não lê nem cobra outro profissional`, { leitura: r.status, escrita: w.status });
  }
  // ADMIN tem acesso a todas as filiais, mas um ID apresentado na filial errada é 404.
  assert.equal((await http(`/comandas/${c.id}/financeiro?filial_id=${seed.outra_filial}`)).status, 404);
  const paid = { id: seed.quitada, date: '2099-01-01' };
  const historicalDate = (await http(scoped(paid.id))).body.data_fechamento;
  await open(paid); assert.equal(await evaluate(`document.querySelectorAll('${form} .financeiro-parcela').length`), 0); await review(); await confirm();
  f = await closed(paid); assert.equal(f.historico.pagamentos.length, 1); assert.deepEqual(JSON.parse(calls.at(-1).raw).pagamentos, []);
  assert.equal((await http(scoped(paid.id))).body.data_fechamento, historicalDate);
  await record('quitação histórica verificada finaliza sem cobrar novamente', { pagamentos: 1 });
  await open({ id: seed.legado, date: '2099-01-02' });
  assert.equal(await evaluate(`!!document.querySelector('${form}')`), false);
  f = await financial(seed.legado); assert.equal(f.situacao, 'nao_verificado'); assert.equal(f.recebido_liquido, null);
  assert.equal((await http(scoped(seed.legado, '/fechamento-financeiro'), { method: 'POST', key: randomUUID(), body: {} })).status, 409);
  await record('legado não verificado bloqueado, sem presumir recebimento');

  const timeout = await appointment(); await open(timeout); await parcel(1, '300.00'); await review(); delayNext = true; await confirm();
  await waitText('Operação aguardando confirmação');
  await waitFor(() => evaluate('document.querySelector(".comanda-financeiro")?.getAttribute("aria-busy")==="false"'), 'timeout Axios concluído e consulta atualizada');
  const first = calls.at(-1); assert.equal((await financial(timeout.id)).historico.pagamentos.length, 1);
  await waitFor(() => evaluate("[...document.querySelectorAll('button')].some(b=>b.textContent==='Recuperar operação original'&&!b.disabled)"), 'recuperação habilitada');
  await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Recuperar operação original').click()");
  await waitText('Operação confirmada.'); await closed(timeout);
  assert.equal(calls.at(-1).key, first.key); assert.equal(calls.at(-1).raw, first.raw); assert.equal((await financial(timeout.id)).historico.pagamentos.length, 1);
  await record('timeout real Axios15s após commit; replay mesma chave/payload sem duplicação', { id: timeout.id });

  const unavailable = await appointment(); await open(unavailable); await parcel(1, '300.00'); await review(); failNext = true; await confirm(); await waitText('Operação aguardando confirmação');
  const failed = calls.at(-1); assert.equal((await financial(unavailable.id)).historico.pagamentos.length, 0);
  await waitFor(() => evaluate('document.querySelector(".comanda-financeiro")?.getAttribute("aria-busy")==="false"'), 'consulta após503');
  await evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent==='Recuperar operação original').click()"); await waitText('Operação confirmada.'); await closed(unavailable);
  assert.equal(calls.at(-1).key, failed.key); assert.equal(calls.at(-1).raw, failed.raw); assert.equal((await financial(unavailable.id)).historico.pagamentos.length, 1);
  await record('503 antes de envio ao backend; recuperação original confirma uma única vez');

  // Prova adicional: da criação ao fechamento, todas as escritas feitas pela UI.
  const uiDate = '2099-03-01';
  await command('browsingContext.navigate', { context, url: 'http://127.0.0.1:5173/agendamentos', wait: 'complete' });
  await waitFor(() => evaluate('!!document.querySelector(".btn-novo")&&!document.querySelector(".btn-novo").disabled'), 'nova agenda disponível');
  await click('.btn-novo');
  await waitFor(() => evaluate('document.querySelectorAll(".modal-box select option").length>3&&!!document.querySelector(".modal-servicos input")'), 'clientes e serviços reais');
  await fill('.modal-box select', seed.cliente); await fill('.modal-box>label:nth-of-type(2) select', seed.usuarios.barbeiro);
  await fill('.modal-box input[type="date"]', uiDate); await fill('.modal-box input[type="time"]', '09:00'); await click('.modal-servicos input'); await click('.modal-btn-salvar');
  await waitFor(() => evaluate('!document.querySelector(".modal-box")&&!!document.querySelector(".appointment-card")'), 'agendamento criado pela UI');
  for (const label of ['Registrar chegada', 'Iniciar atendimento', 'Concluir atendimento']) {
    await waitFor(() => evaluate(`[...document.querySelectorAll('.appointment-card button')].some(b=>b.textContent===${JSON.stringify(label)}&&!b.disabled)`), label);
    await evaluate(`[...document.querySelectorAll('.appointment-card button')].find(b=>b.textContent===${JSON.stringify(label)}).click()`);
  }
  await waitFor(() => evaluate('!document.querySelector(".appointment-card button")'), 'atendimento concluído pela UI');
  const uiPanel = await http(`/comandas/painel?filial_id=${seed.filial}&data_inicio=${uiDate}&data_fim=${uiDate}`);
  const uiComanda = uiPanel.body.itens[0]; assert.equal(uiComanda.status, 'aberta'); assert.equal(uiComanda.data_fechamento, null); assert.equal(uiComanda.atendimento.status, 'concluido');
  await open({ id: uiComanda.id, date: uiDate }); await parcel(1, '300.00'); await review(); await confirm();
  assert.equal((await closed({ id: uiComanda.id })).historico.pagamentos.length, 1);
  await record('ponta a ponta somente UI: criar, chegada, iniciar, concluir mantém aberta, pagar fecha', { id: uiComanda.id });
  evidence.resultado = 'aprovado'; await record('homologação concluída', { posts_ui: calls.length });
} catch (error) {
  await debugPage?.();
  evidence.resultado = 'falhou'; evidence.erro = error.message; await writeFile('/evidencias/homologacao.json', JSON.stringify(evidence, null, 2)); throw error;
} finally {
  ws?.close(); firefox?.kill(); vite?.kill(); proxy.closeAllConnections(); proxy.close(); await rm(profile, { recursive: true, force: true });
}
