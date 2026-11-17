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
let role = 'admin', bloquear = false, atraso = 0;
let reserva = { id: 'reserva', filial_id: filial.id, data: '2099-01-01', hora_inicio: '09:00:00', hora_fim: '09:30:00', barbeiro_id:'p1', atualizado_em:'2026-11-16T12:00:00Z', status:'pendente', cliente:{ nome:'Cliente teste', telefone:'000000' }, barbeiro:profissionais[0], servicos:[{ servico:{ nome:'Corte' } }] };
const historico = [], calls = [];
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type');
  res.setHeader('Access-Control-Allow-Methods', 'GET, PATCH, OPTIONS');
  if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
  const path = new URL(req.url, 'http://local').pathname;
  const reply = (status, data) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
  if (path === '/auth/me') return reply(200, { ...admin, id: role.startsWith('barbeiro') ? 'p1' : admin.id, perfil: role });
  if (path === '/filiais') return reply(200, [filial]);
  if (path === '/usuarios/barbeiros') return reply(200, profissionais);
  if (path === '/agendamentos') return reply(200, reserva.status !== 'cancelado' || new URL(req.url, 'http://local').searchParams.get('incluir_cancelados') === 'true' ? [reserva] : []);
  if (path === '/agendamentos/reserva') return reply(200, reserva);
  if (path === '/agendamentos/reserva/reagendamentos') return reply(200, historico);
  if (path === '/agendamentos/reserva/reagendamento' && req.method === 'PATCH') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw); calls.push(body);
    if (atraso) await new Promise(r => setTimeout(r, atraso));
    if (bloquear) return reply(409, { detail: 'Horário ocupado. Atualize o atendimento.' });
    historico.push({ id:'historico', agendamento_id:reserva.id, data_anterior:reserva.data, hora_inicio_anterior:reserva.hora_inicio, barbeiro_id_anterior:reserva.barbeiro_id, data_nova:body.data, hora_inicio_nova:body.hora_inicio, barbeiro_id_novo:body.barbeiro_id, motivo:body.motivo });
    reserva = { ...reserva, ...body, hora_fim:'11:30:00', barbeiro:profissionais.find(p => p.id === body.barbeiro_id), atualizado_em:'2026-11-16T12:01:00Z' };
    return reply(200, reserva);
  }
  if (path === '/agendamentos/reserva/status' && req.method === 'PATCH') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const body = JSON.parse(raw); calls.push(body);
    if (atraso) await new Promise(r => setTimeout(r, atraso));
    if (bloquear || body.atualizado_em_esperado !== reserva.atualizado_em) return reply(409, { detail:'Agendamento alterado. Atualize antes de cancelar' });
    assert.equal(body.confirmado, true); assert.ok(body.motivo_cancelamento.trim());
    reserva = { ...reserva, status:'cancelado', motivo_cancelamento:body.motivo_cancelamento,
      cancelado_por:admin.id, cancelado_em:'2026-11-17T13:00:00Z', atualizado_em:'2026-11-17T13:00:00Z' };
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
  const click = s => evaluate(`document.querySelector(${JSON.stringify(s)}).click()`);
  const text = t => waitFor(() => evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`), t);
  async function fill(selector, value) { await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:e instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e instanceof HTMLSelectElement?'change':'input',{bubbles:true}));})()`); }
  await command('browsingContext.navigate', { context, url: `${origin}/login`, wait: 'complete' });
  await evaluate("localStorage.setItem('token','token-ficticio')");
  const navigate = () => command('browsingContext.navigate', { context, url: `${origin}/agendamentos`, wait: 'complete' });
  await navigate(); await text('Cliente teste');
  const abrir = () => evaluate("[...document.querySelectorAll('.appointment-card button')].find(b=>b.textContent==='Cancelar agendamento').click()");
  const form = '[role="dialog"] form';
  await abrir(); await text('Confirme o cancelamento desta reserva');
  assert.equal(await evaluate(`document.querySelector('${form} button[type=submit]').disabled`),true);
  for (const width of [1440,768,320]) {
    await command('browsingContext.setViewport',{context,viewport:{width,height:1000}});
    assert.ok(await evaluate("(()=>{const r=document.querySelector('[role=dialog]').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.height<=innerHeight})()"));
  }
  await fill(`${form} textarea`,'Cliente solicitou cancelamento');
  assert.equal(await evaluate(`document.querySelector('${form} button[type=submit]').disabled`),true);
  await click('[role="dialog"] > button'); assert.equal(calls.length,0);
  await text('Cliente teste'); await abrir(); await text('Confirme o cancelamento desta reserva');
  await fill(`${form} textarea`,'Cliente solicitou cancelamento');
  await click(`${form} input[type=checkbox]`); atraso=350;
  await evaluate(`document.querySelector('${form}').requestSubmit();document.querySelector('${form}').requestSubmit()`);
  await text('Agendamento cancelado. O histórico foi preservado.');
  assert.equal(calls.length,1);assert.equal(calls[0].atualizado_em_esperado,'2026-11-16T12:00:00Z');
  await waitFor(()=>evaluate("!document.querySelector('.appointment-card')"),'Cancelado oculto por padrão');
  await click('.agenda-content > label input[type=checkbox]'); await text('Consultar histórico');
  historico.push({id:'h1',agendamento_id:'reserva',data_anterior:'2099-01-01',hora_inicio_anterior:'08:00:00',barbeiro_id_anterior:'p1',data_nova:'2099-01-01',hora_inicio_nova:'09:00:00',barbeiro_id_novo:'p1',motivo:'Ajuste anterior',registrado_em:'2026-11-16T12:00:00Z',registrado_por:admin.id});
  await evaluate("[...document.querySelectorAll('.appointment-card button')].find(b=>b.textContent==='Consultar histórico').click()");
  await text('Cliente solicitou cancelamento');await text(admin.id);await text('Histórico de reagendamentos (1)');
  await click('[role="dialog"] details summary');await text('Ajuste anterior');
  assert.equal(await evaluate(`!!document.querySelector('${form}')`),false);
  await click('[role="dialog"] > button');
  reserva={...reserva,status:'aguardando'};bloquear=true;atraso=0;
  await navigate();await text('Cliente teste');await abrir();await text('Confirme o cancelamento desta reserva');
  await fill(`${form} textarea`,'Outra solicitação');await click(`${form} input[type=checkbox]`);
  await click(`${form} button[type=submit]`);await text('Agendamento alterado. Atualize antes de cancelar');
  assert.equal(await evaluate(`document.querySelector('${form} fieldset').disabled`),true);
  await evaluate(`document.querySelector('${form}').requestSubmit()`);assert.equal(calls.length,2);
  await click('[role="dialog"] > button');
  for(const status of ['em_atendimento','concluido']) {
    reserva.status=status;await navigate();await text('Cliente teste');
    assert.equal(await evaluate("[...document.querySelectorAll('.appointment-card button')].some(b=>b.textContent==='Cancelar agendamento')"),false);
  }
  console.log('PASS Firefox PR59: motivo obrigatório, confirmação, voltar sem escrita, versão, clique duplo, status, consulta de cancelados com autoria e reagendamentos, conflito sem reenvio, bloqueio após início e layout 1440/768/320px. API simulada local.');
  await command('session.end');
} finally {
  ws?.close(); vite?.kill('SIGTERM'); firefox?.kill('SIGTERM'); server.closeAllConnections(); await new Promise(r=>server.close(r));
  await new Promise(r=>setTimeout(r,300)); await rm(profile,{recursive:true,force:true});
}
