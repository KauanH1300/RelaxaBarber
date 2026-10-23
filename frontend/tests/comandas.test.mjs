import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import axios from 'axios';
import { carregarTs } from './helpers/carregarTs.mjs';

const storage = new Map([['token', 'jwt-ficticio']]);
globalThis.localStorage = { getItem: (key) => storage.get(key) ?? null, removeItem: (key) => storage.delete(key) };
globalThis.window = new EventTarget();
const service = await carregarTs('services/comandas.ts');
const { default: api } = await carregarTs('services/api.ts');
const contexto = await carregarTs('services/filialAtiva.ts');
const { CardComanda, Indicadores } = await carregarTs('pages/comandas/ComponentesComanda.tsx');
const { ConteudoDetalhe } = await carregarTs('pages/comandas/DetalheComanda.tsx');
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const comanda = {
  id: '12345678-0000-4000-8000-123456789abc', agendamento_id: 'agendamento-ficticio',
  cliente: { id: 'cliente', nome: 'Cliente de teste' }, profissional: { id: 'profissional', nome: 'Profissional de teste' },
  filial: { id: 'filial-a', nome: 'Unidade A' }, status: 'fechada',
  atendimento: { id: 'agendamento-ficticio', data: '2099-01-02', hora_inicio: '09:00:00', hora_fim: '09:30:00', status: 'concluido' },
  data_abertura: '2099-01-02T12:00:00Z', data_fechamento: '2099-01-02T12:30:00Z',
  total: '25.00', itens: [{ id: 'item', tipo: 'servico', descricao: 'Serviço histórico', quantidade: 2, preco_unitario: '12.50', subtotal: '25.00' }],
};

test('card usa dados, quantidade, unitário, subtotal e status operacional', () => {
  const html = render(CardComanda, { comanda, aoDetalhar() {} });
  for (const text of ['Cliente de teste', 'Profissional de teste', 'Serviço histórico', '2×', '12,50', '25,00', '02/01/2099', '09:00–09:30', 'Fechada', 'Concluído']) assert.ok(html.includes(text), text);
  assert.ok(!html.includes('Pago') && !html.includes('Cobrar'));
  assert.ok(html.includes('CMD · 12345678…9abc'));
  assert.ok(html.includes(`title="${comanda.id}"`));
  assert.ok(html.includes(`aria-label="Ver comanda de Cliente de teste, ${comanda.id}"`));
});

test('card sem itens não inventa serviços', () => {
  assert.match(render(CardComanda, { comanda: { ...comanda, itens: [], total: '0.00' }, aoDetalhar() {} }), /Nenhum item registrado/);
});

test('indicadores usam agregado do servidor e deixam pagamentos indisponíveis', () => {
  const dados = { contagens: { aberta: 9, pendente: 2, fechada: 7, cancelada: 1 }, valor_abertas: '1200.50', pagamentos_disponiveis: false };
  const html = render(Indicadores, { dados, carregando: false });
  for (const text of ['>9<', '>7<', '1.200,50', 'Indisponível', 'não indica quitação']) assert.ok(html.includes(text), text);
  const loading = render(Indicadores, { dados: null, carregando: true });
  assert.match(loading, /aria-busy="true"/);
  assert.ok(loading.includes('—') && !loading.includes('>0<'));
});

test('detalhe exibe filial, datas Recife, itens e UUID inteiro sem ações financeiras', () => {
  const html = render(ConteudoDetalhe, { comanda });
  for (const text of ['Unidade A', '09:00', 'America/Recife', comanda.id, 'agendamento-ficticio', 'Serviço histórico', 'Não comprova pagamento recebido']) assert.ok(html.includes(text), text);
  assert.ok(!html.includes('Cobrar') && !html.includes('Ir para caixa'));
  assert.equal(service.instanteRecife(null), 'Não registrada');
});

test('formatação usa data civil e fuso Recife', () => {
  assert.equal(service.diaRecife(new Date('2026-10-23T01:00:00Z')), '2026-10-22');
  assert.equal(service.dataAtendimento('2099-01-02'), '02/01/2099');
  assert.match(service.moeda('0.00'), /0,00/);
  assert.match(service.instanteRecife('2026-10-22T12:30:00Z'), /09:30/);
});

test('intervalos da paginação incluem páginas finais e vazias', () => {
  assert.equal(service.intervaloPagina(1, 6, 13), '1–6');
  assert.equal(service.intervaloPagina(2, 6, 13), '7–12');
  assert.equal(service.intervaloPagina(3, 6, 13), '13–13');
  assert.equal(service.intervaloPagina(1, 6, 0), '0');
  assert.equal(service.intervaloPagina(4, 6, 13), '0');
});

test('filtros e página são enviados ao servidor com filial autorizada', async () => {
  contexto.mudarContexto('jwt-ficticio', 'filial-a');
  api.defaults.adapter = async (config) => {
    assert.equal(config.url, '/comandas/painel');
    assert.deepEqual(config.params, { busca: 'cliente', profissional_id: 'profissional', data_inicio: '2099-01-01', data_fim: '2099-01-31', status: 'aberta', pagina: 2, tamanho: 6, filial_id: 'filial-a' });
    return { status: 200, data: { total: 12, itens: [comanda] }, headers: {}, config };
  };
  const result = await service.consultarComandas({ busca: 'cliente', profissional_id: 'profissional', data_inicio: '2099-01-01', data_fim: '2099-01-31', status: 'aberta' }, 2);
  assert.equal(result.total, 12);
});

test('detalhe usa UUID inteiro e descarta resposta antiga após troca de filial', async () => {
  contexto.mudarContexto('jwt-ficticio', 'filial-a');
  let liberar, iniciou;
  const pronto = new Promise((resolve) => { iniciou = resolve; });
  api.defaults.adapter = (config) => new Promise((resolve) => {
    assert.equal(config.url, `/comandas/${comanda.id}`);
    liberar = () => resolve({ status: 200, data: comanda, headers: {}, config }); iniciou();
  });
  const pending = service.detalharComanda(comanda.id);
  await pronto;
  contexto.mudarContexto('jwt-ficticio', 'filial-b'); liberar();
  await assert.rejects(pending, axios.isCancel);
});

test('erros de acesso, inexistência, sessão e indisponibilidade são tratados', () => {
  const erro = (status) => new axios.AxiosError('interno', undefined, { url: '/comandas/painel' }, {}, { status, data: {}, headers: {} });
  assert.match(service.erroConsultaComanda(erro(404), true), /não encontrada/);
  assert.match(service.erroConsultaComanda(erro(403)), /acesso a esta unidade/);
  assert.match(service.erroConsultaComanda(erro(503)), /Não foi possível carregar/);
  assert.match(service.erroConsultaComanda(erro(401)), /Sessão expirada/);
});
