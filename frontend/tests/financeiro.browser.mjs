/** Firefox real, Vite e API simulada no loopback. Nenhum serviço remoto. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID, createHash } from 'node:crypto';

const root = fileURLToPath(new URL('../', import.meta.url));
const profile = await mkdtemp(join(tmpdir(), 'rb-financeiro-firefox-'));
const filial = '10000000-0000-4000-8000-000000000001';
const profissional = '20000000-0000-4000-8000-000000000001';
const comandaId = '30000000-0000-4000-8000-000000000001';
const pagamentoAntigo = '40000000-0000-4000-8000-000000000001';
const servicoAdicional = '50000000-0000-4000-8000-000000000001';
const instante = new Date(Date.now() - 3600000).toISOString();
const comanda = {
  id: comandaId, agendamento_id: randomUUID(), filial_id: filial, cliente_id: randomUUID(), barbeiro_id: profissional,
  cliente: { id: randomUUID(), nome: 'Cliente fictício financeiro' }, profissional: { id: profissional, nome: 'Profissional fictício' },
  filial: { id: filial, nome: 'Unidade fictícia' }, status: 'aberta', total: '30.00', data_abertura: instante, data_fechamento: null,
  atendimento: { id: randomUUID(), data: instante.slice(0, 10), hora_inicio: '09:00:00', hora_fim: '09:30:00', status: 'concluido' },
  itens: [{ id: randomUUID(), tipo: 'servico', servico_id: null, descricao: 'Corte fictício', quantidade: 1, preco_unitario: '30.00', subtotal: '30.00' }],
};
let role = 'admin', usuario = profissional, situacao = 'aberto', consultaStatus = 200, perderResposta = false;
let historico, replay, chamadas = [], consultas = 0, paineis = 0, detalhes = 0, rejeitarPost = false, total = 3000, atrasoPost = 0;
let negarReplayItem = 0;
let habilitavel = false;
let ajustes = [];
function reset() {
  ajustes = []; comanda.versao_itens = 0;
  comanda.itens = [{ id: randomUUID(), tipo:'servico',servico_id:servicoAdicional,descricao:'Corte fictício',quantidade:1,preco_unitario:'30.00',subtotal:'30.00',ativo:true }];
  habilitavel = false;
  situacao = 'aberto'; consultaStatus = 200; replay = new Map();
  comanda.status = 'aberta'; comanda.data_fechamento = null; comanda.atendimento.status = 'concluido'; comanda.total = '30.00'; total = 3000; rejeitarPost = false; atrasoPost = 0;
  historico = {
    pagamentos: [{ id: pagamentoAntigo, valor: '10.00', forma: 'pix', recebido_em: instante, registrado_em: instante }],
    estornos: [2, 1].map((valor) => ({ id: randomUUID(), pagamento_id: pagamentoAntigo, valor: `${valor}.00`, motivo: 'Estorno anterior', efetivado_em: instante, registrado_em: instante })),
  };
}
reset();
const dinheiro = (valor) => (valor / 100).toFixed(2);
const centavos = (valor) => Math.round(Number(valor) * 100);
function resumo() {
  const pagos = historico.pagamentos.reduce((s, p) => s + centavos(p.valor), 0);
  const estornos = historico.estornos.reduce((s, e) => s + centavos(e.valor), 0);
  return { comanda_id: comandaId, filial_id: filial, situacao, total: dinheiro(total), pagamentos: situacao === 'nao_verificado' ? null : dinheiro(pagos),
    estornos: situacao === 'nao_verificado' ? null : dinheiro(estornos), recebido_liquido: situacao === 'nao_verificado' ? null : dinheiro(pagos - estornos),
    saldo: situacao === 'nao_verificado' ? null : dinheiro(total - pagos + estornos), historico: situacao === 'nao_verificado' ? { pagamentos: [], estornos: [] } : historico,
    habilitacao: habilitavel ? { origem: 'portal_cliente', conferencia: 'a'.repeat(64), total: dinheiro(total), situacao: comanda.atendimento.status, itens: comanda.itens.map(i=>({id:i.id,servico:servicoAdicional,descricao:i.descricao,quantidade:i.quantidade,preco:i.preco_unitario})) } : null };
}
function previaItem(payload, itemId) {
  if (payload.versao !== comanda.versao_itens) return { erro:'versao_itens_desatualizada' };
  const item = comanda.itens.find(i => i.id === itemId && i.ativo !== false);
  if (!item || situacao !== 'aberto') return { erro:'estado_financeiro_incompativel' };
  const posterior = { ...item };
  if (payload.acao === 'remover') posterior.ativo = false;
  else {
    posterior.quantidade = payload.quantidade;
    if (payload.acao === 'substituir') Object.assign(posterior,{servico_id:servicoAdicional,descricao:'Serviço adicional cadastrado',preco_unitario:'12.50'});
    posterior.subtotal = dinheiro(centavos(posterior.preco_unitario) * posterior.quantidade);
  }
  const novo = total-centavos(item.subtotal)+(posterior.ativo === false ? 0 : centavos(posterior.subtotal));
  const recebido = centavos(resumo().recebido_liquido);
  if (novo < recebido) return { erro:'saldo_insuficiente' };
  const p = {comanda_id:comandaId,item_id:itemId,versao:comanda.versao_itens,anterior:{...item},posterior,total_anterior:dinheiro(total),total:dinheiro(novo),recebido_liquido:dinheiro(recebido),saldo:dinheiro(novo-recebido),exige_fechamento:novo===recebido && recebido>0};
  return {...p,conferencia:createHash('sha256').update(JSON.stringify(p)+payload.motivo+payload.acao).digest('hex')};
}
const server = createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Headers', 'Authorization, Content-Type, Idempotency-Key');
  if (req.method === 'OPTIONS') return res.writeHead(204).end();
  const path = new URL(req.url, 'http://localhost').pathname;
  const reply = (status, data) => { res.writeHead(status, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)); };
  if (path === '/auth/me') return reply(200, { id: usuario, nome: 'Operador fictício', email: 'teste@example.test', perfil: role, ativo: true });
  if (path === '/filiais') return reply(200, [{ id: filial, nome: 'Unidade fictícia', fuso_horario: 'America/Recife' }]);
  if (path === '/usuarios/barbeiros') return reply(200, [comanda.profissional]);
  if (path === '/servicos/') return reply(200, [{ id: servicoAdicional, nome: 'Serviço adicional cadastrado', preco: 12.5, ativo: true }]);
  const saldo = resumo().saldo;
  const estado = situacao === 'nao_verificado' ? 'nao_verificado' : situacao === 'fechado' ? 'fechada' : saldo === '0.00' ? 'aguardando_fechamento' : comanda.atendimento.status === 'concluido' ? 'pagamento_pendente' : 'aberta';
  const projetada = { ...comanda, itens:comanda.itens.filter(i=>i.ativo!==false),status_apresentacao: estado, saldo_financeiro: saldo, fechamento_financeiro_em: situacao === 'fechado' ? comanda.data_fechamento : null };
  if (req.method === 'GET' && path.endsWith('/itens/alteracoes')) return reply(200,ajustes);
  if (path === '/comandas/painel') { paineis++; return reply(200, { itens: [projetada], total: 1, pagina: 1, tamanho: 6, indicadores: { contagens: {}, contagens_apresentacao: { [estado]: 1 }, abertas_verificadas: Number(situacao === 'aberto'), aguardando_pagamento: Number(estado === 'pagamento_pendente'), fechadas_periodo: Number(estado === 'fechada'), valor_abertas: situacao === 'aberto' ? saldo : '0.00', pagamentos_disponiveis: true } }); }
  if (path === `/comandas/${comandaId}`) { detalhes++; return reply(200, projetada); }
  if (path.endsWith('/financeiro')) {
    consultas++;
    return reply(consultaStatus, consultaStatus === 200 ? resumo() : { detail: { codigo: 'acesso_financeiro_negado' } });
  }
  if (req.method === 'POST') {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const payload = JSON.parse(raw), key = req.headers['idempotency-key'];
    if (path.endsWith('/previa')) {
      const p = previaItem(payload,path.split('/').at(-2));
      return reply(p.erro ? 409 : 200,p.erro ? {detail:{codigo:p.erro}} : p);
    }
    chamadas.push({ path, raw, key });
    if (negarReplayItem && path.endsWith('/itens/servicos')) { const status = negarReplayItem; negarReplayItem = 0; return reply(status, {}); }
    if (replay.has(key)) {
      const original = replay.get(key);
      return reply(original.raw === raw && original.path === path ? 200 : 409, original.raw === raw && original.path === path ? original.registro : { detail: { codigo:'conflito_idempotencia' } });
    }
    if (rejeitarPost) { rejeitarPost = false; return reply(422, { detail: { codigo:'entrada_financeira_invalida' } }); }
    if (situacao === 'fechado') return reply(409, { detail: { codigo: 'estado_financeiro_incompativel' } });
    let registro = { id: randomUUID(), ...payload, registrado_em: new Date().toISOString() };
    if (path.endsWith('/alteracoes')) {
      const p = previaItem(payload,path.split('/').at(-2));
      if (p.erro) return reply(409,{detail:{codigo:p.erro}});
      if (p.conferencia !== payload.conferencia) return reply(409,{detail:{codigo:'versao_itens_desatualizada'}});
      if (p.exige_fechamento && !payload.confirmar_fechamento) return reply(409,{detail:{codigo:'confirmacao_ajuste_necessaria'}});
      Object.assign(comanda.itens.find(i=>i.id===p.item_id),p.posterior);total=centavos(p.total);comanda.total=p.total;comanda.versao_itens++;
      if (p.exige_fechamento) {situacao='fechado';comanda.status='fechada';comanda.data_fechamento=registro.registrado_em;}
      registro={...p,acao:payload.acao,motivo:payload.motivo,versao:comanda.versao_itens,registrado_em:registro.registrado_em,registrado_por:usuario,chave_idempotencia:key,fechado:p.exige_fechamento};
      ajustes.push(registro);
    }
    else if (path.endsWith('/habilitacao-financeira')) {
      if (!['admin','recepcao'].includes(role)) return reply(403, {});
      if (!habilitavel || payload.conferencia !== 'a'.repeat(64) || payload.confirmado !== true || !payload.motivo.trim()) return reply(409, { detail:{codigo:'estado_financeiro_incompativel'} });
      situacao='aberto'; habilitavel=false;
    }
    else if (path.endsWith('/itens/servicos')) {
      if (payload.servico_id !== servicoAdicional || !Number.isInteger(payload.quantidade) || payload.quantidade < 1 || payload.quantidade > 999) return reply(422, {});
      total += 1250 * payload.quantidade; comanda.total = dinheiro(total);
      comanda.itens.push({ id: registro.id, tipo: 'servico', servico_id: servicoAdicional, descricao: 'Serviço adicional cadastrado', quantidade: payload.quantidade, preco_unitario: '12.50', subtotal: dinheiro(1250 * payload.quantidade) });
    }
    else if (path.endsWith('/pagamentos')) return reply(409, { detail: { codigo:'estado_financeiro_incompativel' } });
    else if (path.endsWith('/estornos')) historico.estornos.push(registro);
    else if (path.endsWith('/recebimentos') || path.endsWith('/fechamento-financeiro')) {
      const ps = payload.pagamentos ?? [];
      if (ps.length > 16 || ps.some((p) => p.confirmado !== true || centavos(p.valor) <= 0 || !['pix','credito','debito','dinheiro'].includes(p.forma))) return reply(422, { detail:{ codigo:'entrada_financeira_invalida' } });
      if (ps.reduce((s,p) => s + centavos(p.valor),0) > centavos(resumo().saldo)) return reply(409, { detail:{ codigo:'saldo_insuficiente' } });
      if (total === 0 || !ps.length) return reply(409, { detail:{ codigo:'estado_financeiro_incompativel' } });
      historico.pagamentos.push(...ps.map((p) => ({ id:randomUUID(), ...p, registrado_em:new Date().toISOString() })));
      if (resumo().saldo === '0.00') { situacao = 'fechado'; comanda.status = 'fechada'; comanda.data_fechamento = new Date().toISOString(); }
    }
    else return reply(404, {});
    replay.set(key, { path, raw, registro });
    if (atrasoPost) await new Promise((resolve) => setTimeout(resolve, atrasoPost));
    if (perderResposta) { perderResposta = false; return reply(503, { detail: { codigo: 'confirmacao_indeterminada' } }); }
    return reply(200, registro);
  }
  return reply(404, {});
});
const listen = (s) => new Promise((resolve, reject) => { s.once('error', reject); s.listen(0, '127.0.0.1', () => resolve(s.address().port)); });
async function freePort() { const s = createServer(); const port = await listen(s); await new Promise((resolve) => s.close(resolve)); return port; }
async function waitFor(check, label) {
  const end = Date.now() + 20000;
  while (Date.now() < end) { try { if (await check()) return; } catch { /* aguarda render/rede local */ } await new Promise((resolve) => setTimeout(resolve, 100)); }
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
  let sequence = 0; const pending = new Map();
  ws.addEventListener('message', ({ data }) => {
    const body = JSON.parse(data), item = pending.get(body.id);
    if (item) { clearTimeout(item.timer); pending.delete(body.id); body.type === 'error' ? item.reject(new Error(body.message)) : item.resolve(body.result); }
  });
  function command(method, params = {}) {
    const id = ++sequence;
    return new Promise((resolve, reject) => { const timer = setTimeout(() => reject(new Error(method)), 20000); pending.set(id, { resolve, reject, timer }); ws.send(JSON.stringify({ id, method, params })); });
  }
  await command('session.new', { capabilities: { alwaysMatch: {} } });
  const { context } = await command('browsingContext.create', { type: 'tab' });
  async function evaluate(expression) {
    const result = await command('script.evaluate', { expression, target: { context }, awaitPromise: true });
    if (result.type === 'exception') throw new Error(result.exceptionDetails.text);
    if (result.result.type === 'null') return null;
    return result.result.value;
  }
  const click = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
  const waitText = (text) => waitFor(() => evaluate(`document.querySelector('dialog')?.textContent.includes(${JSON.stringify(text)})`), text);
  async function screenshot(name) {
    if (!process.env.COMANDAS_SCREENSHOT_DIR) return;
    const result = await command('browsingContext.captureScreenshot', { context });
    await writeFile(join(process.env.COMANDAS_SCREENSHOT_DIR, `${name}.png`), Buffer.from(result.data, 'base64'));
  }
  async function preencher(selector, valor) {
    await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:e instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(valor)});e.dispatchEvent(new Event(e instanceof HTMLSelectElement?'change':'input',{bubbles:true}));})()`);
  }
  async function abrir() { await click('.comanda-card footer button'); await waitText('Histórico financeiro'); await waitFor(() => evaluate('!document.querySelector(".comanda-financeiro").getAttribute("aria-busy") || document.querySelector(".comanda-financeiro").getAttribute("aria-busy")==="false"'), 'financeiro carregado'); }
  async function fechar() { await click('dialog header button'); await waitFor(() => evaluate('!document.querySelector("dialog")'), 'fechar'); }
  async function navegar() { await command('browsingContext.navigate', { context, url: `${origin}/comandas`, wait: 'complete' }); await waitFor(() => evaluate('!!document.querySelector(".comanda-card")'), 'comandas'); }
  const form = 'form[data-operacao="recebimentos"]';
  const storage = `relaxabarber:financeiro:v1:${profissional}:${filial}:${comandaId}`;
  const aguardarAtualizacao = () => waitFor(() => evaluate('document.querySelector(".comanda-financeiro")?.getAttribute("aria-busy")==="false"'), 'financeiro atualizado');
  async function confirmar() {
    await evaluate('document.querySelector(".financeiro-confirmacao button").click();document.querySelector(".financeiro-confirmacao button")?.click()');
    await waitText('Operação confirmada.');
    await aguardarAtualizacao();
  }
  async function revisar() {
    await click(`${form} button[type="submit"]`); await waitText('Confirmar:');
    if (comanda.status === 'aberta' && situacao === 'aberto') {
      await waitText('Conclua ou cancele a revisão da operação financeira antes de adicionar serviços.');
      assert.equal(await evaluate('document.querySelector(".comanda-adicionar-servico button")?.disabled'), true);
    }
  }
  async function parcela(indice, valor, forma = 'pix', confirmarRecebimento = true) {
    const linha = `${form} .financeiro-parcela:nth-of-type(${indice})`;
    await preencher(`${linha} input[inputmode="decimal"]`, valor);
    await preencher(`${linha} select`, forma);
    if (confirmarRecebimento) await click(`${linha} input[type="checkbox"]`);
  }
  async function estornar(valor, motivo) {
    await evaluate('document.querySelector(".financeiro-estorno").open=true');
    const f = 'form[data-operacao="estornos"]';
    await preencher(`${f} select`, pagamentoAntigo);
    await preencher(`${f} input[inputmode="decimal"]`, valor);
    await preencher(`${f} textarea`, motivo);
    await click(`${f} button[type="submit"]`); await waitText('Confirmar:'); await confirmar();
  }
  await command('browsingContext.navigate', { context, url: `${origin}/login`, wait: 'complete' });
  await evaluate("localStorage.setItem('token','jwt-simulado')");
  await command('browsingContext.setViewport', { context, viewport: { width: 1440, height: 1100 } });
  if (process.env.QA59_ONLY) {
    for (const status of ['pendente', 'aguardando']) {
      reset(); historico = { pagamentos: [], estornos: [] }; comanda.atendimento.status = status;
      await navegar(); await abrir(); await waitText('Pagamentos somente após o início do atendimento.');
      assert.equal(await evaluate(`!!document.querySelector('${form}')`), false);
    }
    for (const status of ['em_atendimento', 'concluido']) {
      reset(); historico = { pagamentos: [], estornos: [] }; comanda.atendimento.status = status;
      await navegar(); await abrir();
      assert.equal(await evaluate(`!!document.querySelector('${form}')`), true);
      await parcela(1, '10', 'dinheiro'); await revisar(); await confirmar();
      assert.equal(resumo().recebido_liquido, '10.00');
      assert.equal(comanda.atendimento.status, status);
    }
    console.log('PASS Firefox PR59: recebimentos bloqueados antes do início com explicação, permitidos em atendimento e após conclusão, confirmação e atualização do saldo. API simulada local.');
  }
  if (process.env.QA_EDICAO_ONLY) {
    reset();historico={pagamentos:[],estornos:[]};
    await navegar();await abrir();
    const editor='.comanda-editar-servicos';
    const editar=()=>click(`${editor} button[aria-label^="Editar quantidade"]`);
    const motivo=()=>preencher(`${editor} textarea`,'Correção fictícia conferida');
    const previa=async()=>{await click(`${editor} form button[type=submit]`);await waitFor(()=>evaluate(`!!document.querySelector('${editor} [aria-label="Revisão do ajuste"]')`),'previa de ajuste');};
    const cancelar=()=>evaluate(`Array.from(document.querySelectorAll('${editor} button')).find(b=>b.textContent==='Cancelar ajuste').click()`);
    const confirmar=()=>click(`${editor} [aria-label="Revisão do ajuste"] button`);
    await editar();await preencher(`${editor} input[type=number]`,'2');await motivo();await previa();
    await waitText('Novo saldo:');assert.equal(chamadas.length,0);await cancelar();assert.equal(comanda.total,'30.00');
    await editar();await preencher(`${editor} input[type=number]`,'2');await motivo();await previa();await confirmar();
    await waitText('Ajuste confirmado.');await aguardarAtualizacao();assert.equal(comanda.total,'60.00');assert.equal(comanda.itens[0].preco_unitario,'30.00');
    await waitFor(()=>evaluate(`!!document.querySelector('${editor} button[aria-label^="Substituir"]')`),'atualizar servicos');
    await click(`${editor} button[aria-label^="Substituir"]`);await motivo();
    await waitFor(()=>evaluate(`document.querySelectorAll('${editor} select option').length>1`),'catalogo');
    await preencher(`${editor} select`,servicoAdicional);await previa();await confirmar();await waitText('Ajuste confirmado.');await aguardarAtualizacao();
    assert.equal(comanda.total,'25.00');assert.equal(comanda.itens[0].preco_unitario,'12.50');
    await fechar();reset();comanda.itens[0].quantidade=3;comanda.itens[0].preco_unitario='10.00';
    historico={pagamentos:[{id:pagamentoAntigo,valor:'10.00',forma:'dinheiro',recebido_em:instante,registrado_em:instante}],estornos:[]};
    await abrir();await editar();await preencher(`${editor} input[type=number]`,'1');await motivo();await previa();
    assert.equal(await evaluate(`document.querySelector('${editor} [aria-label="Revisão do ajuste"] button').disabled`),true);
    const antes=chamadas.length;await cancelar();assert.equal(chamadas.length,antes);assert.equal(comanda.itens[0].quantidade,3);assert.equal(situacao,'aberto');
    await editar();await preencher(`${editor} input[type=number]`,'1');await motivo();await previa();
    await click(`${editor} [aria-label="Revisão do ajuste"] input[type=checkbox]`);perderResposta=true;await confirmar();
    await waitText('Ajuste aguardando confirmação');await aguardarAtualizacao();assert.equal(situacao,'fechado');assert.equal(historico.pagamentos.length,1);
    const original=chamadas.at(-1);await fechar();await abrir();
    await waitFor(()=>evaluate(`!document.querySelector('${editor} aside button').disabled`),'recuperacao disponivel');
    await click(`${editor} aside button`);await waitText('Ajuste e fechamento confirmados');await aguardarAtualizacao();
    assert.equal(chamadas.at(-1).key,original.key);assert.equal(chamadas.at(-1).raw,original.raw);assert.equal(ajustes.length,1);
    await fechar();reset();historico={pagamentos:[],estornos:[]};await abrir();
    await click(`${editor} button[aria-label^="Remover"]`);await motivo();await previa();await confirmar();
    await waitText('Ajuste confirmado.');await aguardarAtualizacao();assert.equal(comanda.total,'0.00');assert.equal(situacao,'aberto');assert.equal(historico.pagamentos.length,0);
    await command('browsingContext.setViewport',{context,viewport:{width:390,height:844}});
    assert.ok(await evaluate('document.querySelector("dialog").scrollWidth<=document.querySelector("dialog").clientWidth'));
    await fechar();reset();role='barbeiro';await navegar();await abrir();
    assert.equal(await evaluate(`!!document.querySelector('${editor} button[aria-label^="Editar quantidade"]')`),false);
    console.log('PASS edição: quantidade histórica, substituição, prévia/cancelamento, OPÇÃO B, timeout/replay após fechamento, remoção a zero, mobile e permissão. API simulada local.');
  }
  if (process.env.QA_NUCLEO_ONLY) {
    reset(); historico = { pagamentos: [], estornos: [] }; comanda.atendimento.status = 'em_atendimento';
    await navegar(); await abrir();
    await parcela(1, '10.00');
    await waitText('Saldo restante após confirmar:');
    await revisar(); await confirmar();
    assert.equal(resumo().saldo, '20.00'); assert.equal(situacao, 'aberto');
    await waitText('Valor restante a confirmar:');
    assert.ok(await evaluate('document.querySelector(".financeiro-resumo").textContent.includes("20,00")'));
    await parcela(1, '20.01'); await click(`${form} button[type="submit"]`); await waitText('não pode exceder');
    assert.equal(chamadas.length, 1);
    await parcela(1, '20.00', 'dinheiro', false); await click(`${form} button[type="submit"]`); await waitText('Confirme que cada valor');
    assert.equal(chamadas.length, 1);
    await click(`${form} input[type="checkbox"]`);
    await waitText('será fechada automaticamente');
    perderResposta = true;
    await revisar(); await click('.financeiro-confirmacao button');
    await waitText('Operação aguardando confirmação'); await aguardarAtualizacao();
    assert.equal(situacao, 'fechado'); assert.equal(resumo().saldo, '0.00');
    const original = chamadas.at(-1);
    await click('.financeiro-pendente button'); await waitText('Operação confirmada.'); await aguardarAtualizacao();
    assert.equal(chamadas.at(-1).raw, original.raw); assert.equal(chamadas.at(-1).key, original.key);
    assert.equal(historico.pagamentos.length, 2);
    assert.equal(comanda.atendimento.status, 'em_atendimento');
    assert.equal(await evaluate('!!document.querySelector("form[data-operacao=recebimentos]")'), false);
    await fechar(); reset(); total = 0; comanda.total = '0.00'; historico = { pagamentos: [], estornos: [] };
    await abrir(); await waitText('Gratuidade exige fluxo próprio');
    assert.equal(await evaluate('!!document.querySelector("form[data-operacao=recebimentos]")'), false);
    console.log('PASS núcleo: recebimento parcial em atendimento, saldo, excesso, confirmação, quitação automática, timeout/replay e total zero.');
  }
  if (!process.env.QA59_ONLY && !process.env.QA_HABILITACAO_ONLY && !process.env.QA_NUCLEO_ONLY && !process.env.QA_EDICAO_ONLY) {
  await navegar(); await abrir();
  assert.equal(await evaluate('document.querySelectorAll(".financeiro-resumo>div").length'), 3);
  await waitText('Valor Total'); await waitText('Valor Recebido');
  for (const [name, width, height] of [['desktop', 1440, 1100], ['tablet', 900, 1000], ['mobile', 390, 844], ['mobile-320', 320, 740]]) {
    await command('browsingContext.setViewport', { context, viewport: { width, height } });
    assert.ok(await evaluate('document.querySelector("dialog").scrollWidth <= document.querySelector("dialog").clientWidth'), `detalhe sem overflow: ${name}`);
    assert.ok(await evaluate(`!!document.querySelector('[aria-label="Cliente da comanda"]') && !!document.querySelector('[aria-label="Profissional responsável"]')`));
    assert.equal(await evaluate('getComputedStyle(document.querySelector(".comanda-financeiro button[type=submit]")).backgroundColor'), 'rgb(229, 176, 68)');
    await evaluate('document.querySelector("dialog").scrollTop=0');
    await screenshot(`detalhe-${name}`);
    await evaluate('document.querySelector(".financeiro-resumo").scrollIntoView({block:"start"})');
    await screenshot(`financeiro-${name}`);
  }
  await command('browsingContext.setViewport', { context, viewport: { width: 1440, height: 1100 } });
  assert.equal(await evaluate('document.querySelectorAll(".financeiro-historico>li").length'), 1);
  assert.equal(await evaluate('document.querySelectorAll(".financeiro-historico ol li").length'), 2);

  await waitText('Situação financeira: Pagamento pendente');
  assert.equal(await evaluate('document.querySelectorAll(".comanda-detalhe-dados dt").length'), 3);
  assert.equal(await evaluate('document.querySelector("dialog").textContent.includes("estados distintos")'), false);
  assert.equal(await evaluate('document.querySelectorAll(".comanda-financeiro .financeiro-situacao").length'), 1);
  assert.equal(await evaluate('document.querySelector(".comanda-atendimento-indicador").textContent'), 'Concluído');
  assert.equal(await evaluate('document.querySelector(".comanda-detalhe-informacoes").textContent.includes("America/Recife")'), false);
  assert.equal(await evaluate('document.querySelector(".comanda-detalhe-informacoes").textContent.includes("histórico")'), false);

  await evaluate('document.querySelector(".financeiro-historico-area").open=true');
  await click('.financeiro-historico button');
  assert.equal(await evaluate('document.querySelector(".financeiro-estorno").open'), true);
  assert.equal(await evaluate('document.activeElement===document.querySelector(".financeiro-estorno select")'), true);
  await preencher('form[data-operacao="estornos"] input[inputmode="decimal"]', '7.01');
  await preencher('form[data-operacao="estornos"] textarea', 'Devolução confirmada');
  await click('form[data-operacao="estornos"] button[type="submit"]');
  await waitText('valor dentro do limite disponível');
  assert.equal(chamadas.length, 0);
  await fechar();
  for (const width of [320, 390, 768, 900, 1440]) {
    await command('browsingContext.setViewport', { context, viewport: { width, height: 1000 } });
    assert.ok(await evaluate(`(()=>{
      const h=document.querySelector('.comanda-card-identificacao'), id=h.firstElementChild, badge=h.lastElementChild;
      const original=badge.textContent;
      const labels=['Aberta','Pagamento pendente','Aguardando fechamento','Pagamento não verificado','Fechada','Cancelada','Financeiro restrito'];
      const ok=labels.every(label=>{
        badge.textContent=label;
        const a=id.getBoundingClientRect(),b=badge.getBoundingClientRect(),r=h.getBoundingClientRect();
        return Math.abs((a.top+a.bottom)/2-(b.top+b.bottom)/2)<2 && a.right<=b.left && b.right<=r.right+1 && badge.scrollWidth<=badge.clientWidth+1;
      });
      badge.textContent=original; id.focus();
      return ok && getComputedStyle(id.querySelector('.comanda-id-completo')).display==='block';
    })()`), 'badges alinhados e identificador completo acessível: '+width);
  }
  await command('browsingContext.setViewport', { context, viewport: { width: 1440, height: 1100 } });
  await abrir();
  await parcela(1, '23.01');
  await click(`${form} button[type="submit"]`); await waitText('não pode exceder');
  assert.equal(chamadas.length, 0, 'excesso não envia POST');
  await parcela(1, '23.00', 'debito', false);
  await click(`${form} button[type="submit"]`); await waitText('Confirme que cada valor');
  assert.equal(chamadas.length, 0, 'sem confirmação explícita não envia POST');
  await fechar(); await abrir();
  await estornar('2.00', 'Correção de pagamento antigo');
  await estornar('1.00', 'Outro estorno parcial');
  assert.equal(historico.estornos.length, 4);
  const consultasAntes = { paineis, detalhes };
  await parcela(1, '10.00');
  await click(`${form} fieldset>button[type="button"]`);
  await parcela(2, '16.00', 'credito');
  await revisar();
  await evaluate('document.querySelector(".financeiro-confirmacao").scrollIntoView({block:"center"})');
  await screenshot('confirmacao-combinada');
  await confirmar();
  await waitText('Situação financeira: Fechada');
  assert.equal(resumo().saldo, '0.00');
  assert.equal(chamadas.length, 3, 'dois estornos e um único fechamento integral');
  assert.ok(chamadas.every((r) => !r.path.endsWith('/pagamentos')));
  assert.deepEqual(JSON.parse(chamadas.at(-1).raw).pagamentos.map((p) => p.valor), ['10.00','16.00']);
  await waitFor(() => paineis > consultasAntes.paineis && detalhes > consultasAntes.detalhes, 'detalhes e indicadores consultados automaticamente');
  await waitFor(() => evaluate('document.querySelector(".comandas-indicadores article strong")?.textContent==="0"'), 'indicador aberto atualizado');
  assert.equal(await evaluate('document.querySelector(".financeiro-situacao")?.textContent'), 'Situação financeira: Fechada');
  assert.equal(await evaluate('!!document.querySelector(".financeiro-form")'), false);
  await fechar(); await abrir();
  assert.equal(await evaluate('document.querySelectorAll(".financeiro-historico>li").length'), 3);
  await fechar(); reset(); perderResposta = true;
  await abrir(); await parcela(1, '23.00'); await revisar(); await click('.financeiro-confirmacao button');
  await waitText('Operação aguardando confirmação');
  await aguardarAtualizacao();
  const original = chamadas.at(-1);
  assert.equal(await evaluate('document.querySelectorAll(".financeiro-historico>li").length'), 2);
  await fechar(); await navegar(); await abrir();
  await waitText('Operação aguardando confirmação');
  assert.equal(await evaluate(`sessionStorage.getItem(${JSON.stringify(storage)})!==null`), true);
  await click('.financeiro-pendente button'); await waitText('Operação confirmada.');
  assert.deepEqual(chamadas.at(-1), original, 'replay mantém chave e payload originais');
  assert.equal(historico.pagamentos.length, 2);
  await waitFor(() => evaluate('document.querySelectorAll(".financeiro-historico>li").length===2'), 'sem duplicação visual');

  await fechar(); reset(); await abrir();
  await parcela(1, '23.00'); await revisar();
  await evaluate('window.rbSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw new Error("storage indisponivel")}');
  assert.equal(await evaluate('(()=>{try{sessionStorage.setItem("teste-storage","1");return false}catch{return true}})()'), true, 'falha de storage realmente injetada');
  const antesStorage = chamadas.length;
  await click('.financeiro-confirmacao button'); await waitText('Nenhuma requisição foi enviada');
  assert.equal(chamadas.length, antesStorage);
  await evaluate('Storage.prototype.setItem=window.rbSetItem;delete window.rbSetItem');
  rejeitarPost = true;
  await click('.financeiro-confirmacao button'); await waitText('Verifique valor'); await aguardarAtualizacao();
  assert.equal(await evaluate('!!document.querySelector(".financeiro-pendente")'), false, '422 inicial libera correção após consultar estado');
  assert.equal(situacao, 'aberto');
  await revisar(); await confirmar();

  // O sucesso do POST continua válido se a limpeza local ou o GET posterior falhar.
  await fechar(); reset(); await abrir();
  await parcela(1, '23.00'); await revisar();
  await evaluate('window.rbRemoveItem=Storage.prototype.removeItem;Storage.prototype.removeItem=function(){throw new Error("limpeza indisponivel")}');
  await click('.financeiro-confirmacao button'); await waitText('registro temporário não pôde ser removido'); await aguardarAtualizacao();
  assert.equal(situacao, 'fechado');
  assert.equal(await evaluate('!!document.querySelector(".financeiro-pendente")'), true);
  const limpezaOriginal = chamadas.at(-1);
  await evaluate('Storage.prototype.removeItem=window.rbRemoveItem;delete window.rbRemoveItem');
  await click('.financeiro-pendente button'); await waitText('Operação confirmada.'); await aguardarAtualizacao();
  assert.deepEqual(chamadas.at(-1), limpezaOriginal);
  assert.equal(historico.pagamentos.length, 2);
  await fechar(); reset(); await abrir();
  await parcela(1, '23.00'); await revisar(); consultaStatus = 503;
  const antesFalhaConsulta = chamadas.length;
  await click('.financeiro-confirmacao button'); await waitText('Não foi possível consultar o financeiro');
  assert.equal(situacao, 'fechado');
  assert.equal(chamadas.length, antesFalhaConsulta + 1);
  assert.equal(await evaluate(`sessionStorage.getItem(${JSON.stringify(storage)})`), null);
  assert.equal(await evaluate('!!document.querySelector(".financeiro-form")'), false);
  consultaStatus = 200; await click('.comanda-financeiro header button'); await waitText('Situação financeira: Fechada');

  // Fechar o diálogo durante o POST não pode deixar os indicadores desatualizados.
  await fechar(); reset(); await navegar(); await abrir();
  await evaluate(`(()=>{const b=document.querySelector('${form} fieldset>button[type="button"]');for(let i=0;i<20;i++)b.click()})()`);
  assert.equal(await evaluate('document.querySelectorAll(".financeiro-parcela").length'), 16);
  assert.equal(await evaluate(`document.querySelector('${form} fieldset>button[type="button"]').disabled`), true);
  await fechar(); await abrir(); await parcela(1, '23.00'); await revisar();
  atrasoPost = 1000;
  const painelFechadoAntes = paineis, postFechadoAntes = chamadas.length;
  await click('.financeiro-confirmacao button');
  await waitFor(() => chamadas.length > postFechadoAntes, 'POST iniciado'); await fechar();
  const operacaoDuranteEnvio = chamadas.at(-1);
  await abrir(); await waitText('Operação aguardando confirmação');
  await waitFor(() => paineis > painelFechadoAntes, 'indicadores atualizados mesmo sem diálogo');
  await waitFor(() => evaluate('document.querySelector(".comandas-indicadores article strong")?.textContent==="0"'), 'indicador após fechar diálogo');
  assert.notEqual(await evaluate(`sessionStorage.getItem(${JSON.stringify(storage)})`), null, 'instância desmontada não apaga intenção carregada pela nova');
  await click('.financeiro-pendente button'); await waitText('Operação confirmada.'); await aguardarAtualizacao();
  assert.deepEqual(chamadas.at(-1), operacaoDuranteEnvio);
  assert.equal(await evaluate(`sessionStorage.getItem(${JSON.stringify(storage)})`), null);
  assert.equal(historico.pagamentos.length, 2);

  await fechar(); reset();
  const legadoKey = randomUUID(), legadoPayload = { valor:'10.00', forma:'pix', recebido_em:instante };
  replay.set(legadoKey, { path:`/comandas/${comandaId}/pagamentos`, raw:JSON.stringify(legadoPayload), registro:historico.pagamentos[0] });
  await evaluate(`sessionStorage.setItem(${JSON.stringify(storage)},${JSON.stringify(JSON.stringify({chave:legadoKey,operacao:'pagamentos',payload:legadoPayload}))})`);
  await abrir(); await waitText('Registro antigo'); await click('.financeiro-pendente button'); await waitText('Operação confirmada.'); await aguardarAtualizacao();
  assert.equal(historico.pagamentos.length, 1, 'replay antigo não insere pagamento');
  assert.ok(chamadas.at(-1).path.endsWith('/pagamentos'));
  await fechar();
  const inexistente = { chave:randomUUID(), operacao:'pagamentos', payload:legadoPayload };
  await evaluate(`sessionStorage.setItem(${JSON.stringify(storage)},${JSON.stringify(JSON.stringify(inexistente))})`);
  await abrir(); await click('.financeiro-pendente button'); await waitText('O estado atual'); await aguardarAtualizacao();
  assert.equal(await evaluate('!!document.querySelector(".financeiro-pendente")'), true, 'replay rejeitado não apaga pendência anterior');
  assert.equal(await evaluate('!!document.querySelector(".financeiro-form")'), false);
  await fechar(); await evaluate(`sessionStorage.removeItem(${JSON.stringify(storage)})`);
  await evaluate(`sessionStorage.setItem(${JSON.stringify(storage)},'registro corrompido')`);
  await abrir(); await waitText('Não foi possível recuperar o registro temporário');
  assert.equal(await evaluate('!!document.querySelector(".financeiro-form")'), false);
  await fechar(); await evaluate(`sessionStorage.removeItem(${JSON.stringify(storage)})`);


  reset(); historico = { pagamentos:[], estornos:[] };
  await abrir();
  assert.equal(await evaluate('!!document.querySelector(".financeiro-estorno")'), false, 'sem pagamentos não oferece estorno');
  await fechar(); reset();
  historico.estornos.push({id:randomUUID(), pagamento_id:pagamentoAntigo, valor:'7.00', motivo:'Devolução confirmada', efetivado_em:instante, registrado_em:instante});
  await abrir();
  assert.equal(await evaluate('!!document.querySelector(".financeiro-estorno")'), false, 'pagamento integralmente estornado não oferece estorno');
  await fechar();
  reset(); historico = { pagamentos:[{ id:pagamentoAntigo, valor:'30.00', forma:'dinheiro', recebido_em:instante, registrado_em:instante }], estornos:[] };
  await abrir();
  assert.equal(await evaluate(`!!document.querySelector('${form}')`), false);
  assert.equal(historico.pagamentos.length, 1);
  await fechar(); reset(); total = 0; comanda.total = '0.00'; historico = { pagamentos:[], estornos:[] };
  await abrir(); await waitText('Gratuidade exige fluxo próprio');
  assert.equal(await evaluate(`!!document.querySelector('${form}')`), false);
  await fechar(); reset(); comanda.atendimento.status = 'em_atendimento'; await abrir();
  assert.equal(await evaluate(`!!document.querySelector('${form}')`), true, 'atendimento não concluído permite recebimento');
  await fechar(); situacao = 'nao_verificado'; await abrir();
  await waitText('Histórico financeiro não verificado');
  assert.equal(await evaluate('!!document.querySelector(".financeiro-form")'), false);
  await fechar(); reset();
  for (const status of [403, 404]) {
    consultaStatus = status; await click('.comanda-card footer button');
    if (status === 403) {
      // O interceptor existente invalida o contexto e desmonta os detalhes ao
      // revalidar filiais. Não pode permanecer histórico de um escopo revogado.
      await waitFor(() => evaluate('!document.querySelector("dialog") && !!document.querySelector(".comanda-card")'), '403 revalida filial e remove detalhes');
    } else await waitText('Comanda não encontrada');
    assert.equal(await evaluate('!!document.querySelector(".financeiro-historico")'), false);
    if (status === 404) await fechar();
  }
  consultaStatus = 200;
  for (const perfil of ['recepcao', 'barbeiro', 'barbeiro_chefe']) {
    role = perfil; await navegar(); await abrir();
    assert.equal(await evaluate('!!document.querySelector(".financeiro-estorno")'), false);
    await fechar();
  }
  for (const perfil of ['barbeiro', 'barbeiro_chefe']) {
    role = perfil; usuario = randomUUID(); await navegar(); const antes = consultas;
    await click('.comanda-card footer button'); await waitText('restrita às suas próprias comandas');
    await waitText('Seu perfil não tem permissão para adicionar serviços nesta comanda.');
    assert.equal(consultas, antes, 'não consulta financeiro de outro profissional'); await fechar();
  }
  role = 'admin'; usuario = profissional; await navegar(); await abrir();
  await command('browsingContext.setViewport', { context, viewport: { width: 390, height: 844 } });
  assert.ok(await evaluate('document.querySelector("dialog").scrollWidth <= document.querySelector("dialog").clientWidth'));
  for (let i = 0; i < 10; i++) {
    await command('input.performActions', { context, actions: [{ type: 'key', id: 'tab', actions: [{ type: 'keyDown', value: '\uE004' }, { type: 'keyUp', value: '\uE004' }] }] });
    assert.ok(await evaluate('!!document.activeElement.closest("dialog")'));
  }
  await fechar(); reset(); await navegar(); await abrir();
  await waitFor(() => evaluate('!document.querySelector(".comanda-adicionar-servico button")?.disabled'), 'adicionar habilitado após consulta financeira');
  assert.equal(await evaluate('document.querySelector(".comanda-adicionar-servico").textContent.includes("Atendimento concluído não significa fechamento financeiro")'), false);
  assert.equal(await evaluate('document.querySelector(".comanda-adicionar-servico").textContent.includes("Pagamento pendente. Adicionar um serviço")'), false);
  await command('browsingContext.setViewport', { context, viewport: { width: 320, height: 740 } });
  await evaluate('document.querySelector(".comanda-adicionar-servico").scrollIntoView({block:"center"})');
  await screenshot('diagnostico-pagamento-pendente-320');
  await fechar();
  for (const [operacional, financeiro, mensagem] of [
    ['fechada', 'aberto', 'Comanda operacionalmente fechada.'],
    ['fechada', 'fechado', 'Comanda financeiramente fechada.'],
    ['aberta', 'nao_verificado', 'Classificação financeira não verificada.'],
    ['cancelada', 'aberto', 'Comanda ou atendimento cancelado.'],
  ]) {
    reset(); comanda.status = operacional; situacao = financeiro;
    await navegar(); await abrir(); await waitText(mensagem);
    assert.equal(await evaluate('[...document.querySelectorAll(".comanda-adicionar-servico button")].some(b=>b.textContent==="Adicionar serviço")'), false);
    assert.ok(await evaluate('document.querySelector("dialog").scrollWidth <= document.querySelector("dialog").clientWidth'), 'mensagem sem overflow em 320 px');
    await evaluate('document.querySelector(".comanda-adicionar-servico").scrollIntoView({block:"center"})');
    await screenshot(`diagnostico-${operacional}-${financeiro}-320`);
    await fechar();
  }
  reset(); await navegar(); await abrir();
  await waitFor(() => evaluate('!document.querySelector(".comanda-adicionar-servico button")?.disabled'), 'ação novamente habilitada em aberta verificada');
  await click('.comanda-adicionar-servico button');
  await waitFor(() => evaluate('document.querySelectorAll(".comanda-adicionar-servico select option").length===2'), 'catálogo cadastrado');
  await preencher('.comanda-adicionar-servico select', servicoAdicional);
  await preencher('.comanda-adicionar-servico input', '2');
  assert.ok(await evaluate('document.querySelector(".comanda-adicionar-servico").textContent.includes("25,00")'));
  assert.ok(await evaluate('document.querySelector("form[data-operacao=recebimentos] fieldset").disabled'), 'recebimento bloqueado durante edição');
  perderResposta = true; const inclusoesAntes = chamadas.length;
  await evaluate('document.querySelector(".comanda-adicionar-servico button[type=submit]").click();document.querySelector(".comanda-adicionar-servico button[type=submit]")?.click()');
  await waitText('Inclusão aguardando confirmação');
  await waitFor(() => chamadas.length > inclusoesAntes && evaluate('document.querySelector(".comanda-adicionar-servico")?.getAttribute("aria-busy")==="false"'), 'resposta incerta');
  assert.equal(chamadas.length, inclusoesAntes + 1, 'clique duplo envia uma operação');
  const originalItem = chamadas.at(-1);
  await fechar(); await abrir();
  await waitText('Inclusão aguardando confirmação');
  await waitFor(() => evaluate('!document.querySelector(".comanda-adicionar-servico aside button")?.disabled'), 'recuperação liberada');
  negarReplayItem = 403;
  await click('.comanda-adicionar-servico aside button');
  await waitFor(() => evaluate('!document.querySelector("dialog") && !!document.querySelector(".comanda-card")'), 'contexto revalidado após 403');
  await abrir(); await waitText('Inclusão aguardando confirmação');
  await waitFor(() => evaluate('!document.querySelector(".comanda-adicionar-servico aside button")?.disabled'), 'recuperação após revalidar acesso');
  negarReplayItem = 422;
  await click('.comanda-adicionar-servico aside button');
  await waitText('Verifique o serviço ativo');
  await waitFor(() => evaluate('!document.querySelector(".comanda-adicionar-servico aside button")?.disabled'), 'intenção preservada após replay negado');
  assert.equal(chamadas.at(-1).key, originalItem.key);
  await click('.comanda-adicionar-servico aside button');
  await waitText('Serviço adicionado.');
  assert.equal(chamadas.at(-1).key, originalItem.key); assert.equal(chamadas.at(-1).raw, originalItem.raw);
  await waitFor(() => evaluate('document.querySelectorAll(".comanda-tabela-itens tbody tr").length===2 && document.querySelector(".comanda-detalhe-total").textContent.includes("55,00")'), 'itens e total atualizados');
  await waitFor(() => evaluate('document.querySelector(".financeiro-resumo").textContent.includes("55,00")'), 'resumo financeiro atualizado');
  await waitFor(() => evaluate('document.querySelectorAll(".comandas-indicadores article strong")[1].textContent.includes("48,00")'), 'indicador de saldo atualizado');
  assert.ok(await evaluate('document.querySelector("dialog").scrollWidth<=document.querySelector("dialog").clientWidth'), 'tabela rola sem alargar modal móvel');
  console.log('PASS financeiro integral e inclusão: permissões, atualização, valores, clique duplo, confirmação incerta, reabertura/replay, bloqueio mútuo, mobile e teclado. API simulada local.');
  await fechar();
  }
  // Cenários novos podem rodar isoladamente, sem repetir toda a suíte anterior.
  if (!process.env.QA59_ONLY && !process.env.QA_NUCLEO_ONLY && !process.env.QA_EDICAO_ONLY) {
  for (const perfil of ['admin','recepcao']) {
    reset();role=perfil;usuario=profissional;situacao='nao_verificado';habilitavel=true;
    historico={pagamentos:[],estornos:[]};
    await navegar();await abrir();await waitText('Habilitar financeiro da reserva pública');
    assert.equal(await evaluate('document.querySelector(".comanda-financeiro form button[type=submit]").disabled'),true);
    await preencher('.comanda-financeiro form textarea','Reserva conferida pela equipe');
    await click('.comanda-financeiro form input[type=checkbox]');
    await waitFor(()=>evaluate('!document.querySelector(".comanda-financeiro form button[type=submit]").disabled'),'conferencia explicita');
    const antes=chamadas.length;
    await click('.comanda-financeiro form button[type=submit]');await waitText('Confirmar: Habilitar');
    assert.equal(chamadas.length,antes,'revisao nao envia operacao');
    perderResposta=true;
    await evaluate('document.querySelector(".financeiro-confirmacao button").click();document.querySelector(".financeiro-confirmacao button")?.click()');
    await waitText('Operação aguardando confirmação');await aguardarAtualizacao();
    assert.equal(chamadas.length,antes+1,'clique duplo preserva envio unico');
    const original=chamadas.at(-1);
    await fechar();await abrir();await waitText('Operação aguardando confirmação');
    await waitFor(()=>evaluate('!document.querySelector(".financeiro-pendente button").disabled'),'replay disponivel');
    await click('.financeiro-pendente button');
    await waitFor(()=>evaluate('!document.querySelector(".financeiro-pendente")'),'habilitacao recuperada');
    assert.equal(chamadas.at(-1).key,original.key);assert.equal(chamadas.at(-1).raw,original.raw);
    assert.equal(historico.pagamentos.length,0);assert.equal(comanda.status,'aberta');
    assert.equal(chamadas.at(-1).path.endsWith('/habilitacao-financeira'),true);
    await waitText('Saldo a receber');
    await command('browsingContext.setViewport',{context,viewport:{width:390,height:844}});
    assert.ok(await evaluate('document.querySelector("dialog").scrollWidth<=document.querySelector("dialog").clientWidth'));
    await fechar();
  }
  for (const perfil of ['barbeiro','barbeiro_chefe','admin']) {
    reset();role=perfil;situacao='nao_verificado';habilitavel=perfil!=='admin';
    await navegar();await abrir();
    assert.equal(await evaluate('!!document.querySelector(".comanda-financeiro form")'),false,'nao habilita barbeiros nem legado');
    await fechar();
  }
  console.log('PASS habilitacao portal: ADMIN/RECEPCAO, conferencia e confirmacao, clique duplo, resposta incerta, reabertura e replay, ausencia de pagamentos, isolamento de perfis/legado e mobile. API simulada.');
  }
  await command('session.end');
} finally {
  ws?.close(); vite?.kill('SIGTERM'); firefox?.kill('SIGTERM');
  server.closeAllConnections(); await new Promise((resolve) => server.close(resolve));
  await new Promise((resolve) => setTimeout(resolve, 300));
  await rm(profile, { recursive: true, force: true });
}
