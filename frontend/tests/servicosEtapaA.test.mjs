import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement as h } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';

globalThis.localStorage = { getItem: () => null };
globalThis.window = new EventTarget();
const { default: api } = await carregarTs('services/api.ts');
const { listarServicos, consultarServico, criarServico, atualizarServico } = await carregarTs('services/servico.ts');
const { FormServico } = await carregarTs('pages/servicos/FormServico.tsx');

test('formulário aceita comissão zero e delimita percentual entre 0 e 100', () => {
  const html = renderToStaticMarkup(h(MemoryRouter, null, h(FormServico)));
  const campo = html.match(/<input[^>]*placeholder="Ex: 40"[^>]*>/)?.[0];
  assert.ok(campo);
  for (const atributo of ['min="0"', 'max="100"', 'step="0.01"', 'value="0"', 'required=""']) {
    assert.ok(campo.includes(atributo), atributo);
  }
});

test('consumidores aceitam catálogo sem comissão e consulta administrativa por ID', async () => {
  const chamadas = [];
  const catalogo = { id: 'servico-teste', nome: 'Corte', preco: 0, tempo_estimado: 30, ativo: true };
  api.defaults.adapter = async (config) => {
    chamadas.push({ method: config.method, url: config.url, data: config.data });
    return { status: 200, statusText: 'OK', headers: {}, config,
      data: config.url === '/servicos/' && config.method === 'get'
        ? [catalogo] : { ...catalogo, comissao_padrao: 0 } };
  };
  const lista = await listarServicos();
  assert.equal(lista.data[0].preco, 0);
  assert.equal('comissao_padrao' in lista.data[0], false);
  const detalhe = await consultarServico(catalogo.id);
  assert.equal(detalhe.data.comissao_padrao, 0);
  const dados = { nome: 'Corte', preco: 0, tempo_estimado: 30, comissao_padrao: 0 };
  await criarServico(dados);
  await atualizarServico(catalogo.id, { comissao_padrao: 100 });
  assert.deepEqual(chamadas.map(({ method, url }) => [method, url]), [
    ['get', '/servicos/'], ['get', '/servicos/servico-teste'],
    ['post', '/servicos/'], ['put', '/servicos/servico-teste'],
  ]);
  assert.equal(JSON.parse(chamadas[2].data).comissao_padrao, 0);
  assert.equal(JSON.parse(chamadas[3].data).comissao_padrao, 100);
});
