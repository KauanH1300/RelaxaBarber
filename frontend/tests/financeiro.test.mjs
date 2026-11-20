import assert from 'node:assert/strict';
import test from 'node:test';
import axios from 'axios';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { carregarTs } from './helpers/carregarTs.mjs';

const memoria = new Map();
globalThis.sessionStorage = { getItem: (k) => memoria.get(k) ?? null, setItem: (k, v) => memoria.set(k, v), removeItem: (k) => memoria.delete(k) };
globalThis.localStorage = { getItem: () => 'token-teste' };
globalThis.window = new EventTarget();
const f = await carregarTs('services/financeiro.ts');
const { default: api } = await carregarTs('services/api.ts');
const contexto = await carregarTs('services/filialAtiva.ts');
const { HistoricoComanda } = await carregarTs('pages/comandas/HistoricoComanda.tsx');
const comanda = { id: 'comanda', filial_id: 'filial', barbeiro_id: 'barbeiro', status: 'fechada', atendimento: { status: 'concluido' } };
const resumo = { situacao: 'aberto', total: '30.00', pagamentos: '10.00', estornos: '0.00', recebido_liquido: '10.00', saldo: '20.00' };
const chave = '11111111-1111-4111-8111-111111111111';

test('dinheiro usa centavos e rejeita valores fora do contrato', () => {
  assert.equal(f.centavos('10,01'), 1001);
  assert.equal(f.decimal(f.centavos('0.30') - f.centavos('0.10')), '0.20');
  for (const invalido of ['-1', '1e2', 'NaN', '1.001', '100000000.00', '']) assert.throws(() => f.centavos(invalido));
});
test('perfis de barbeiros só consultam as próprias comandas', () => {
  for (const perfil of ['barbeiro', 'barbeiro_chefe']) {
    assert.equal(f.podeConsultar({ perfil, id: 'barbeiro' }, comanda), true);
    assert.equal(f.podeConsultar({ perfil, id: 'outro' }, comanda), false);
  }
  for (const perfil of ['admin', 'recepcao']) assert.equal(f.podeConsultar({ perfil, id: 'outro' }, comanda), true);
});
test('legado e fechamento bloqueiam, atendimento em andamento permite recebimento', () => {
  assert.equal(f.podeMovimentar(comanda, resumo), true);
  for (const situacao of ['nao_verificado', 'fechado']) assert.equal(f.podeMovimentar(comanda, { situacao }), false);
  assert.equal(f.podeMovimentar({ ...comanda, status: 'aberta' }, resumo), true);
  for (const status of ['cancelada', 'pendente']) assert.equal(f.podeMovimentar({ ...comanda, status }, resumo), false);
  assert.equal(f.podeMovimentar({ ...comanda, atendimento: { status: 'em_atendimento' } }, resumo), true);
});
test('datas exigem instante válido, sem futuro e respeitam retroatividade', () => {
  assert.throws(() => f.dataEfetiva('', true));
  assert.throws(() => f.dataEfetiva('inválido', true));
  assert.throws(() => f.dataEfetiva(new Date(Date.now() + 3600000).toISOString(), true));
  const antiga = new Date(Date.now() - 169 * 3600000).toISOString();
  assert.throws(() => f.dataEfetiva(antiga, false), /168/);
  assert.equal(f.dataEfetiva(antiga, true), antiga);
  assert.throws(() => f.dataEfetiva(antiga, true, new Date().toISOString()), /anteceder/);
});
test('pendência é isolada por usuário, filial e comanda; limpa somente chave correspondente', () => {
  const storage = f.chaveStorage('usuario', comanda);
  const pendente = { chave, operacao: 'pagamentos', payload: { valor: '10.00', forma: 'pix', recebido_em: '2026-01-01T12:00:00Z' } };
  // Registro anterior à Etapa 3: não criar um novo pagamento avulso.
  memoria.set(storage, JSON.stringify(pendente));
  assert.deepEqual(f.lerPendente(storage), pendente);
  assert.notEqual(storage, f.chaveStorage('outro', comanda));
  assert.notEqual(storage, f.chaveStorage('usuario', { ...comanda, filial_id: 'outra' }));
  f.limparPendente(storage, { ...pendente, chave: 'outra' });
  assert.deepEqual(f.lerPendente(storage), pendente);
  f.limparPendente(storage, pendente);
  assert.equal(f.lerPendente(storage), null);
  memoria.set(storage, JSON.stringify({ ...pendente, payload: { ...pendente.payload, token: 'indevido' } }));
  assert.throws(() => f.lerPendente(storage));
  memoria.delete(storage);
});
test('mocks: fechamento integral e retry preservam lista, chave, ordem e payload', async () => {
  contexto.mudarContexto('token-teste', 'filial');
  const chamadas = [];
  const registros = new Map();
  let recebimentos = 0;
  let perderResposta = true;
  api.defaults.adapter = async (config) => {
    chamadas.push({ url: config.url, body: config.data, chave: config.headers.get('Idempotency-Key') });
    const escopo = `${config.url}:${config.headers.get('Idempotency-Key')}`;
    if (!registros.has(escopo)) {
      assert.ok(config.url.endsWith('/fechamento-financeiro'));
      recebimentos += JSON.parse(config.data).pagamentos.reduce((s, p) => s + f.centavos(p.valor), 0);
      registros.set(escopo, { total: '30.00', recebido_liquido: '30.00' });
    }
    // A escrita foi confirmada no servidor, mas a primeira resposta se perdeu.
    if (perderResposta) { perderResposta = false; throw new axios.AxiosError('timeout intermediário', undefined, config, undefined, { status: 408 }); }
    return { data: registros.get(escopo), status: 200, statusText: 'OK', headers: {}, config };
  };
  const pendente = { chave, operacao: 'fechamento-financeiro', payload: { motivo: null, pagamentos: [
    { valor: '10.00', forma: 'pix', recebido_em: '2026-01-01T12:00:00Z', confirmado: true },
    { valor: '20.00', forma: 'dinheiro', recebido_em: '2026-01-01T12:00:00Z', confirmado: true },
  ] } };
  await assert.rejects(f.enviarFinanceiro(comanda, pendente), (erro) => f.resultadoIncerto(erro));
  await f.enviarFinanceiro(comanda, pendente);
  assert.deepEqual(chamadas[0], chamadas[1]);
  assert.equal(recebimentos, 3000, 'replay não duplica nenhuma parcela');
  await assert.rejects(f.enviarFinanceiro(comanda, { chave, operacao: 'pagamentos', payload: {} }), /recebimentos confirmados/);
});
test('timeout HTTP, falhas 5xx e conflito de chave preservam operação', () => {
  for (const status of [408, 500, 502, 503, 504]) assert.equal(f.resultadoIncerto({ response: { status } }), true);
  assert.equal(f.resultadoIncerto({ response: { status: 409, data: { detail: { codigo: 'conflito_idempotencia' } } } }), true);
  assert.equal(f.resultadoIncerto({ response: { status: 422 } }), false);
  assert.equal(f.resultadoIncerto(new axios.AxiosError('timeout', 'ECONNABORTED')), true);
  for (const status of [403, 404]) assert.match(f.erroFinanceiro({ response: { status } }), /permissão|indisponível/);
});

const instante = '2026-01-01T12:00:00Z';
const historico = {
  pagamentos: [
    { id: 'pagamento-antigo', valor: '10.50', forma: 'pix', recebido_em: instante, registrado_em: instante },
    { id: 'outro-pagamento', valor: '20.00', forma: 'credito', recebido_em: instante, registrado_em: instante },
  ],
  estornos: [
    { id: 'estorno-1', pagamento_id: 'pagamento-antigo', valor: '2.00', motivo: 'Correção parcial', efetivado_em: instante, registrado_em: instante },
    { id: 'estorno-2', pagamento_id: 'pagamento-antigo', valor: '1.50', motivo: 'Segunda correção', efetivado_em: instante, registrado_em: instante },
  ],
};
test('histórico associa múltiplos estornos e calcula limite líquido exato por pagamento', () => {
  const pagamentos = f.pagamentosComEstornos(historico);
  assert.equal(pagamentos[0].estornado, '3.50');
  assert.equal(pagamentos[0].liquido, '7.00');
  assert.equal(pagamentos[0].estornos.length, 2);
  assert.equal(pagamentos[1].estornado, '0.00');
  assert.equal(pagamentos[1].liquido, '20.00');
  assert.deepEqual(historico.pagamentos.map((p) => p.valor), ['10.50', '20.00']);
});
test('reabertura usa somente histórico persistido do GET, sem duplicar POSTs locais', async () => {
  contexto.mudarContexto('token-teste', 'filial');
  let consultas = 0;
  api.defaults.adapter = async (config) => {
    assert.equal(config.method, 'get');
    assert.equal(config.url, '/comandas/comanda/financeiro');
    assert.equal(config.params.filial_id, 'filial');
    consultas++;
    return { data: { ...resumo, historico }, status: 200, statusText: 'OK', headers: {}, config };
  };
  const primeira = await f.consultarFinanceiro(comanda);
  const reaberta = await f.consultarFinanceiro(comanda);
  assert.equal(consultas, 2);
  assert.deepEqual(primeira, reaberta);
  const html = renderToStaticMarkup(createElement(HistoricoComanda, { resumo: reaberta }));
  assert.equal((html.match(/Identificação do pagamento/g) ?? []).length, 2);
  for (const texto of ['Correção parcial', 'Segunda correção', '7,00', '3,50', 'Crédito', 'Registrado em', 'Recebido em']) assert.ok(html.includes(texto), texto);
});
test('legado não apresenta lista vazia como quitação e financeiro fechado mantém histórico', () => {
  const render = (dados) => renderToStaticMarkup(createElement(HistoricoComanda, { resumo: dados }));
  const legado = render({ ...resumo, situacao: 'nao_verificado', historico: { pagamentos: [], estornos: [] } });
  assert.match(legado, /não comprova dívida ou pagamento/);
  assert.ok(!legado.includes('Nenhum pagamento registrado'));
  const fechado = render({ ...resumo, situacao: 'fechado', historico });
  assert.match(fechado, /pagamento-antigo/);
  assert.match(fechado, /Segunda correção/);
  assert.equal(f.podeMovimentar(comanda, { ...resumo, situacao: 'fechado' }), false);
});
test('consultar histórico após resposta incerta não apaga chave e payload pendentes', async () => {
  const storage = f.chaveStorage('usuario', comanda);
  const pendente = { chave, operacao: 'pagamentos', payload: { valor: '10.00', forma: 'pix', recebido_em: instante } };
  memoria.set(storage, JSON.stringify(pendente));
  await f.consultarFinanceiro(comanda);
  assert.deepEqual(f.lerPendente(storage), pendente);
  f.limparPendente(storage, pendente);
});

const dataLocal = new Date(Date.now() - 3600000).toISOString();
const parcela = (valor, forma = 'pix') => ({ valor, forma, confirmado: true });
test('composição integral usa centavos, métodos reais e somente o restante líquido', () => {
  const p = f.prepararFechamento(resumo, [parcela('10,01'), parcela('9,99', 'credito')], dataLocal, '', false);
  assert.deepEqual(p.pagamentos.map((r) => r.valor), ['10.01', '9.99']);
  assert.ok(p.pagamentos.every((r) => r.confirmado === true));
  for (const ps of [[], [parcela('19.99')], [parcela('20.01')], [parcela('0')], [parcela('20', 'fiado')], [parcela('20', 'credito_loja')], [{ ...parcela('20'), confirmado: false }], Array(17).fill(parcela('1'))]) {
    assert.throws(() => f.prepararFechamento(resumo, ps, dataLocal, '', false));
  }
  for (const situacao of ['nao_verificado', 'fechado']) assert.throws(() => f.prepararFechamento({ ...resumo, situacao }, [parcela('20')], dataLocal, '', true));
});
test('quitação anterior finaliza sem cobrança e total zero exige motivo', () => {
  assert.deepEqual(f.prepararFechamento({ ...resumo, saldo: '0.00' }, [], '', '', false).pagamentos, []);
  assert.throws(() => f.prepararFechamento({ ...resumo, total: '0.00', saldo: '0.00' }, [], '', '', true));
  assert.equal(f.prepararFechamento({ ...resumo, total: '0.00', saldo: '0.00' }, [], '', 'Cortesia', true).motivo, 'Cortesia');
});
test('pendência integral sobrevive à reabertura sem substituição ou alteração de dados', async () => {
  const storage = f.chaveStorage('usuario', comanda);
  const p = { chave, operacao: 'fechamento-financeiro', payload: f.prepararFechamento(resumo, [parcela('20')], dataLocal, '', true) };
  f.salvarPendente(storage, p);
  const recuperada = f.lerPendente(storage);
  assert.deepEqual(recuperada, p);
  assert.throws(() => f.salvarPendente(storage, { ...p, chave: crypto.randomUUID() }));
  f.limparPendente(storage, { ...p, payload: { motivo: 'outro' } });
  assert.deepEqual(f.lerPendente(storage), p);
  let chamada;
  api.defaults.adapter = async (config) => { chamada = config; return { data: {}, status: 200, statusText: 'OK', headers: {}, config }; };
  await f.recuperarFinanceiro(comanda, storage);
  assert.equal(chamada.headers.get('Idempotency-Key'), chave);
  assert.deepEqual(JSON.parse(chamada.data), p.payload);
  await assert.rejects(f.recuperarFinanceiro({ ...comanda, filial_id: 'outra' }, storage));
  f.limparPendente(storage, p);
});
test('recuperação aceita histórico antigo, mas novos avulsos não são persistidos ou enviados', async () => {
  const storage = f.chaveStorage('usuario', comanda);
  const p = { chave, operacao: 'pagamentos', payload: { valor: '10.00', forma: 'pix', recebido_em: instante } };
  assert.throws(() => f.salvarPendente(storage, p));
  memoria.set(storage, JSON.stringify(p));
  let chamada;
  api.defaults.adapter = async (config) => { chamada = config; return { data: {}, status: 200, statusText: 'OK', headers: {}, config }; };
  await f.recuperarFinanceiro(comanda, storage);
  assert.equal(chamada.url, '/comandas/comanda/pagamentos');
  assert.deepEqual(JSON.parse(chamada.data), p.payload);
  assert.deepEqual(f.lerPendente(storage), p);
  f.limparPendente(storage, p);
  for (const payload of [{ motivo: null }, {}]) {
    memoria.set(storage, JSON.stringify({ chave, operacao: 'fechamento-financeiro', payload }));
    assert.deepEqual(f.lerPendente(storage).payload, payload);
  }
  memoria.delete(storage);
});
test('armazenamento aninhado inválido bloqueia e preserva o registro original', () => {
  const storage = f.chaveStorage('usuario', comanda);
  for (const ps of [[{ valor:'20.00', forma:'pix', recebido_em:instante, confirmado:false }], [{ valor:'20.00', forma:'pix', recebido_em:instante, confirmado:true, token:'indevido' }], Array(17).fill({ valor:'1.00', forma:'pix', recebido_em:instante, confirmado:true })]) {
    const raw = JSON.stringify({ chave, operacao:'fechamento-financeiro', payload:{ pagamentos:ps } });
    memoria.set(storage, raw);
    assert.throws(() => f.lerPendente(storage));
    assert.equal(memoria.get(storage), raw);
  }
  memoria.delete(storage);
});

test('estorno no histórico exige pagamento com líquido positivo e permissão', () => {
  const render = (dados, permitido = true) => renderToStaticMarkup(createElement(HistoricoComanda, {
    resumo: dados, aoEstornar: permitido ? () => {} : undefined,
  }));
  assert.ok(!render({ ...resumo, historico: { pagamentos: [], estornos: [] } }).includes('Estornar pagamento'));
  assert.ok(!render({ ...resumo, historico }, false).includes('Estornar pagamento'));
  assert.ok(!render({ ...resumo, situacao: 'fechado', historico }).includes('Estornar pagamento'));
  assert.ok(!render({ ...resumo, situacao: 'nao_verificado', historico }).includes('Estornar pagamento'));
  const html = render({ ...resumo, historico });
  assert.ok(html.includes('Estornar pagamento pagamento-antigo'));
  assert.ok(html.includes('7,00'));
  const completo = { pagamentos: historico.pagamentos.slice(0, 1), estornos: [
    ...historico.estornos, { ...historico.estornos[0], id: 'restante', valor: '7.00' },
  ] };
  assert.ok(!render({ ...resumo, historico: completo }).includes('Estornar pagamento'));
  assert.equal(historico.estornos.length, 2);
});
