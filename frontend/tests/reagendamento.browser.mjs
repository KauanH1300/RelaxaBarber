/** Firefox real com API simulada no loopback; sem banco ou credenciais reais. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'rb-reagendamento-'));
const filial = { id: '10000000-0000-4000-8000-000000000001', nome: 'Unidade teste', fuso_horario: 'America/Recife' };
const admin = { id: '20000000-0000-4000-8000-000000000001', nome: 'Admin teste', email: 'admin@example.test', perfil: 'admin', ativo: true };
const profissionais = [ { id: 'p1', nome: 'Profissional Um' }, { id: 'p2', nome: 'Profissional Dois' } ];
let role = 'admin', bloquear = false, atraso = 0, perderResposta = false;
let reserva = { id: 'reserva', filial_id: filial.id, data: '2099-01-01', hora_inicio: '09:00:00', hora_fim: '09:30:00', barbeiro_id:'p1', atualizado_em:'2026-11-16T12:00:00Z', status:'pendente', cliente:{ nome:'Cliente teste', telefone:'000000' }, barbeiro:profissionais[0], servicos:[{ servico:{ nome:'Corte' } }] };
const historico = [], calls = [], criacoes = [], consultasSugestoes = [];
const escritasBloqueio = [];
const idBloqueio = '30000000-0000-4000-8000-000000000001';
const rotaBloqueio = '/agendamentos/bloqueios';
let bloqueio;
let criado;
async function perderRespostaBloqueio(res) {
  res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Length': '100' });
  res.write('{');
  await new Promise(resolve => setTimeout(resolve, 100));
  res.destroy();
}
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type, Idempotency-Key');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  const url = new URL(req.url, 'http://local');
  const path = url.pathname;
  const reply = (status, data) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
  if (path === '/auth/me') return reply(200, { ...admin, id: role.startsWith('barbeiro') ? 'p1' : admin.id, perfil: role });
  if (path === '/filiais') return reply(200, [filial]);
  if (path === '/clientes/pesquisa') return reply(200, [{ id: 'cliente', nome: 'Cliente teste', telefone: '000000' }]);
  if (path === '/servicos/') return reply(200, [{ id: 'corte', nome: 'Corte', preco: 20, tempo_estimado: 30 }]);
  if (path === '/usuarios/barbeiros') return reply(200, profissionais);
  if (path === '/agendamentos' && req.method === 'POST') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw); criacoes.push(body);
    if (criacoes.length === 1) return reply(422, { detail: 'Horário fora do expediente.' });
    if (criado) return reply(201, criado);
    criado = { id: 'novo', data: body.data };
    return reply(408, {});
  }
  if (path === '/agendamentos') return reply(200, [reserva]);
  if (path === rotaBloqueio && req.method === 'POST') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw);
    const chave = req.headers['idempotency-key'];
    escritasBloqueio.push({ chave, body });
    if (escritasBloqueio.length === 1) return reply(409, { detail: 'Conflito de bloqueio de teste.' });
    if (escritasBloqueio.length === 2) return reply(408, {});
    bloqueio = { ...body, id: idBloqueio, revogado_em: null };
    return perderRespostaBloqueio(res);
  }
  if (path === rotaBloqueio) return reply(200, bloqueio && !bloqueio.revogado_em ? [bloqueio] : []);
  if (path.startsWith(`${rotaBloqueio}/cadastros/`)) {
    return bloqueio && path.endsWith(`/${escritasBloqueio[2].chave}`) ? reply(200, bloqueio) : reply(404, {});
  }
  if (path === `${rotaBloqueio}/${idBloqueio}` && req.method === 'DELETE') {
    escritasBloqueio.push({ removido: idBloqueio });
    if (escritasBloqueio.length === 4) return reply(408, {});
    bloqueio.revogado_em = '2026-11-23T12:00:00Z';
    return perderRespostaBloqueio(res);
  }
  if (path === `${rotaBloqueio}/${idBloqueio}`) return reply(200, bloqueio);
  if (path === '/agendamentos/sugestoes') {
    consultasSugestoes.push(Object.fromEntries(url.searchParams));
    return reply(200, [{ hora_inicio: '11:00', barbeiro_id: 'p2', barbeiro: 'Profissional Dois' }]);
  }
  if (path === '/agendamentos/reserva') return reply(200, reserva);
  if (path === '/agendamentos/reserva/reagendamentos') return reply(200, historico);
  if (path === '/agendamentos/reserva/reagendamento' && req.method === 'PATCH') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw); calls.push(body);
    if (atraso) await new Promise(r => setTimeout(r, atraso));
    if (bloquear) return reply(409, { detail: 'Horário ocupado. Atualize o atendimento.' });
    if (body.atualizado_em_esperado !== reserva.atualizado_em) return reply(409, { detail: 'Versão atualizada.' });
    const hora = body.hora_inicio.slice(0, 5);
    const fim = `${hora.slice(0, 2)}:30:00`;
    historico.push({ id:String(historico.length), registrado_por:admin.id, agendamento_id:reserva.id,
      data_anterior:reserva.data, hora_inicio_anterior:reserva.hora_inicio, hora_fim_anterior:reserva.hora_fim,
      barbeiro_id_anterior:reserva.barbeiro_id, data_nova:body.data, hora_inicio_nova:hora, hora_fim_nova:fim,
      barbeiro_id_novo:body.barbeiro_id, motivo:body.motivo });
    reserva = { ...reserva, ...body, hora_fim:fim, barbeiro:profissionais.find(p => p.id === body.barbeiro_id), atualizado_em:`2026-11-16T12:0${historico.length}:00Z` };
    if (perderResposta) {
      perderResposta = false;
      res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Length': '100' });
      res.write('{');
      await new Promise(resolve => setTimeout(resolve, 200));
      return res.destroy();
    }
    return reply(200, reserva);
  }
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
  const click = async s => {
    const seletor = JSON.stringify(s);
    await waitFor(() => evaluate(`document.querySelector(${seletor})?.disabled === false || document.querySelector(${seletor})?.tagName === 'SUMMARY'`), s);
    await evaluate(`document.querySelector(${seletor}).click()`);
  };
  const text = async t => {
    try { await waitFor(() => evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`), t); }
    catch (error) { throw new Error(`${error.message}. Modal: ${await evaluate("document.querySelector('[role=dialog]')?.innerText ?? '(fechado)'")}. POST=${criacoes.length}; PATCH=${calls.length}`); }
  };
  async function fill(selector, value) { await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e instanceof HTMLSelectElement?'change':'input',{bubbles:true}));})()`); }
  await command('browsingContext.navigate', { context, url: `${origin}/login`, wait: 'none' });
  await waitFor(() => evaluate(`location.origin === ${JSON.stringify(origin)} && document.readyState !== 'loading'`), 'página de login');
  await evaluate("localStorage.setItem('token','token-ficticio')");
  const navigate = async () => {
    await command('browsingContext.navigate', { context, url: `${origin}/agendamentos`, wait: 'interactive' });
  };
  await navigate(); await text('Cliente teste');
  const formularioBloqueio = '[aria-labelledby="bloqueio-titulo"] form';
  const botaoTexto = async nome => {
    const expressao = `[...document.querySelectorAll('button')].find(b => b.textContent.trim() === ${JSON.stringify(nome)} && !b.disabled)`;
    await waitFor(() => evaluate(`!!(${expressao})`), nome);
    await evaluate(`(${expressao}).click()`);
  };
  await click('.btn-bloquear');
  await fill(`${formularioBloqueio} select`, 'p2');
  await fill(`${formularioBloqueio} [name=inicio]`, '10:00');
  await fill(`${formularioBloqueio} [name=fim]`, '10:30');
  await fill(`${formularioBloqueio} [name=motivo]`, 'Motivo fica na aba');
  await botaoTexto('Confirmar bloqueio'); await text('Conflito de bloqueio de teste.');
  assert.equal(await evaluate(`document.querySelector('${formularioBloqueio} [name=motivo]').value`), 'Motivo fica na aba');
  await botaoTexto('Confirmar bloqueio'); await text('O resultado ainda não foi confirmado.');
  await navigate(); await text('Há uma operação pendente.');
  await click('.btn-bloquear');
  assert.equal(await evaluate(`document.querySelector('${formularioBloqueio} [name=inicio]').value`), '10:00');
  assert.equal(await evaluate(`document.querySelector('${formularioBloqueio} [name=motivo]').value`), 'Motivo fica na aba');
  await botaoTexto('Conferir operação'); await text('A criação ainda não foi encontrada.');
  assert.equal(escritasBloqueio.length, 2);
  await botaoTexto('Repetir criação'); await text('O resultado ainda não foi confirmado.');
  assert.deepEqual(escritasBloqueio[1], escritasBloqueio[2]);
  await botaoTexto('Conferir operação'); await text('Bloqueio criado com sucesso.');
  assert.equal(escritasBloqueio.length, 3);
  await evaluate('window.confirm = () => true');
  await botaoTexto('Remover bloqueio'); await text('O resultado ainda não foi confirmado.');
  await navigate(); await text('Há uma operação pendente.');
  await botaoTexto('Conferir operação'); await text('O bloqueio continua ativo.');
  assert.equal(escritasBloqueio.length, 4);
  await botaoTexto('Repetir remoção'); await text('O resultado ainda não foi confirmado.');
  assert.deepEqual(escritasBloqueio[3], escritasBloqueio[4]);
  await botaoTexto('Conferir operação'); await text('Bloqueio removido com sucesso.');
  assert.equal(escritasBloqueio.length, 5);
  await waitFor(() => evaluate("![...document.querySelectorAll('button')].some(b => b.textContent === 'Remover bloqueio')"), 'bloqueio removido da lista');

  const botaoReagendar = "[...document.querySelectorAll('.appointment-card button')].find(b=>b.textContent==='Reagendar')";
  const abrir = async () => {
    await waitFor(() => evaluate(`(${botaoReagendar})?.disabled === false`), 'ação de reagendamento disponível');
    await evaluate(`(${botaoReagendar}).click()`);
  };
  await abrir(); await text('Novo horário e profissional');
  const form = '[role="dialog"] form';
  assert.equal(await evaluate(`document.querySelector('${form} input[type="date"]').value`), '2099-01-01');
  for (const width of [1440, 768, 320]) {
    await command('browsingContext.setViewport', { context, viewport: { width, height: 1000 } });
    assert.ok(await evaluate("(()=>{const r=document.querySelector('[role=dialog]').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.height<=innerHeight})()"), `modal acessível em ${width}px`);
  }
  await fill(`${form} input[type="date"]`, '2099-01-02');
  await click(`${form} section[aria-label="Sugestões de horários"] > button`);
  await click(`${form} section[aria-label="Sugestões de horários"] li button`);
  assert.equal(await evaluate(`document.querySelector('${form} input[type="time"]').value`), '11:00');
  assert.equal(await evaluate(`document.querySelector('${form} select').value`), 'p2');
  assert.deepEqual(consultasSugestoes[0], { data: '2099-01-02', filial_id: filial.id, agendamento_id: reserva.id });
  atraso = 350;
  await evaluate(`document.querySelector('${form}').requestSubmit();document.querySelector('${form}').requestSubmit()`);
  await text('Atendimento reagendado com sucesso.');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].atualizado_em_esperado, '2026-11-16T12:00:00Z');
  assert.equal(calls[0].barbeiro_id, 'p2');
  assert.equal(await evaluate('!!document.querySelector("[role=dialog]")'), false);
  await waitFor(() => evaluate("[...document.querySelectorAll('.appointment-card')].some(c=>c.textContent.includes('11:00'))"), 'agenda atualizada após reagendamento');
  await abrir(); await text('Histórico de reagendamentos (1)');
  await click('[role="dialog"] details summary'); await text('01/01/2099');
  bloquear = true;
  await fill(`${form} input[type="time"]`, '12:00');
  await click(`${form} button[type="submit"]`); await text('Horário ocupado. Atualize o atendimento.');
  await waitFor(() => evaluate(`!document.querySelector('${form} fieldset').disabled`), 'edição após conflito');
  assert.equal(await evaluate(`document.querySelector('${form} input[type="time"]').value`), '12:00');
  assert.equal(calls.length, 2, 'conflito não provoca repetição de escrita');
  bloquear = false; perderResposta = true;
  await fill(`${form} input[type="time"]`, '13:00');
  await fill(`${form} input[maxlength="1000"]`, 'Pedido do cliente');
  await click(`${form} button[type="submit"]`); await text('O resultado ainda não foi confirmado');
  assert.equal(await evaluate(`document.querySelector('${form} input[maxlength="1000"]').value`), 'Pedido do cliente');
  await click(`${form} button[type="submit"]`); await text('Atendimento reagendado com sucesso.');
  assert.deepEqual(calls[2], calls[3], 'nova tentativa mantém a mesma versão e os mesmos dados');
  assert.equal(historico.length, 2, 'a tentativa posterior não duplica o histórico');

  const botaoNovo = "[...document.querySelectorAll('.btn-novo')].find(b=>b.textContent.trim()==='Novo agendamento')";
  await waitFor(() => evaluate(`(${botaoNovo})?.disabled === false`), 'ação de criação disponível');
  await evaluate(`(${botaoNovo}).click()`);
  await text('Dados do atendimento');
  const novo = '[aria-labelledby="novo-agendamento-titulo"]';
  await waitFor(() => evaluate(`!document.querySelector('${novo} select').matches(':disabled')`), 'clientes e serviços disponíveis');
  await fill(`${novo} select`, 'cliente');
  await fill(`${novo} label:nth-of-type(2) select`, 'p1');
  await fill(`${novo} input[type="time"]`, '09:00');
  await click(`${novo} input[type="checkbox"]`);
  await fill(`${novo} input[type="number"]`, '40');
  await click(`${novo} section[aria-label="Sugestões de horários"] > button`);
  await click(`${novo} section[aria-label="Sugestões de horários"] li button`);
  assert.equal(await evaluate(`document.querySelector('${novo} input[type="time"]').value`), '11:00');
  assert.equal(await evaluate(`document.querySelector('${novo} label:nth-of-type(2) select').value`), 'p2');
  assert.equal(consultasSugestoes[1].duracao_min, '40');
  assert.equal(consultasSugestoes[1].servicos_ids, 'corte');
  await fill(`${novo} input[type="time"]`, '09:00');
  await click(`${novo} .modal-btn-salvar`); await text('Horário fora do expediente.');
  assert.equal(await evaluate(`document.querySelector('${novo} input[type="number"]').value`), '40');
  await fill(`${novo} input[type="time"]`, '10:00');
  await click(`${novo} .modal-btn-salvar`); await text('O resultado ainda não foi confirmado');
  await click(`${novo} .modal-btn-salvar`); await text('Solicitação confirmada. Confira o atendimento na agenda.');
  assert.notEqual(criacoes[0].chave_idempotencia, criacoes[1].chave_idempotencia);
  assert.deepEqual(criacoes[1], criacoes[2], 'a confirmação mantém a chave e o formulário');
  for (const perfil of ['barbeiro', 'barbeiro_chefe']) {
    role = perfil; await navigate(); await text('Cliente teste');
    assert.equal(await evaluate("[...document.querySelectorAll('.appointment-card button')].some(b=>b.textContent==='Reagendar')"), false);
  }
  role = 'recepcao'; await navigate(); await text('Cliente teste');
  assert.ok(await evaluate("[...document.querySelectorAll('.appointment-card button')].some(b=>b.textContent==='Reagendar')"));
  for (const status of ['em_atendimento', 'concluido', 'cancelado']) {
    reserva.status = status; await navigate(); await text('Cliente teste');
    assert.equal(await evaluate("[...document.querySelectorAll('.appointment-card button')].some(b=>b.textContent==='Reagendar')"), false);
  }
  console.log('PASS Agenda Firefox: criação e reagendamento, rejeição, timeout, perda de resposta, recuperação sem duplicidade, rascunho, permissões e modal responsivo. API simulada.');
  await command('session.end');
} finally {
  ws?.close(); vite?.kill('SIGTERM'); firefox?.kill('SIGTERM'); server.closeAllConnections(); await new Promise(r => server.close(r));
  await new Promise(r => setTimeout(r, 300)); await rm(profile, { recursive: true, force: true, maxRetries: 12, retryDelay: 250 });
}
