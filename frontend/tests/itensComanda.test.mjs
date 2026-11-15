import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { carregarTs } from './helpers/carregarTs.mjs';
const map = new Map();
globalThis.localStorage = { getItem: () => null, removeItem() {} };
globalThis.window = new EventTarget();
globalThis.sessionStorage = { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), removeItem: (k) => map.delete(k) };
const s = await carregarTs('services/itensComanda.ts');
const { ItensComanda } = await carregarTs('pages/comandas/ComponentesComanda.tsx');
const id = '10000000-0000-4000-8000-000000000001';
const c = { id, filial_id: 'filial', barbeiro_id: 'barbeiro', status: 'aberta', status_apresentacao: 'pagamento_pendente', atendimento: { status: 'concluido' } };
const p = { chave: id, payload: { servico_id: id, quantidade: 2 } };
test('somente comanda aberta verificada e própria para ambos os barbeiros', () => {
  for (const perfil of ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe']) {
    assert.equal(s.permiteInclusao({ id: 'barbeiro', perfil }, c), true);
    if (perfil.startsWith('barbeiro')) assert.equal(s.permiteInclusao({ id: 'outro', perfil }, c), false);
  }
  for (const status of ['fechada', 'cancelada', 'pendente']) assert.equal(s.permiteInclusao({ id: 'a', perfil: 'admin' }, { ...c, status }), false);
  for (const status_apresentacao of ['nao_verificado', 'restrito', 'fechada', undefined]) assert.equal(s.permiteInclusao({ id: 'a', perfil: 'admin' }, { ...c, status_apresentacao }), false);
});
test('intenção original persiste e não pode ser substituída após timeout', () => {
  const k = s.chaveInclusao('usuario', c);
  s.salvarInclusao(k, p); s.salvarInclusao(k, p);
  assert.deepEqual(s.lerInclusao(k), p);
  assert.throws(() => s.salvarInclusao(k, { ...p, payload: { ...p.payload, quantidade: 3 } }));
  s.limparInclusao(k, { ...p, chave: 'outro' }); assert.deepEqual(s.lerInclusao(k), p);
  s.limparInclusao(k, p); assert.equal(s.lerInclusao(k), null);
});
test('registro corrompido, quantidade manipulada e campos extras bloqueados', () => {
  for (const quantidade of [0, -1, 1000, 1.5, '2', true]) assert.throws(() => s.salvarInclusao('teste', { ...p, payload: { ...p.payload, quantidade } }));
  assert.throws(() => s.salvarInclusao('teste', { ...p, payload: { ...p.payload, preco: 1 } }));
  map.set('teste', '{'); assert.throws(() => s.lerInclusao('teste'));
});
test('tabela sem ações fictícias mantém valores históricos e cabeçalhos acessíveis', () => {
  const html = renderToStaticMarkup(createElement(ItensComanda, { tabela: true, comanda: { itens: [{ id, tipo: 'servico', descricao: 'Corte histórico', quantidade: 2, preco_unitario: '12.50', subtotal: '25.00' }] } }));
  for (const texto of ['Descrição', 'Categoria', 'Quantidade', 'Valor unitário', 'Subtotal', 'Serviço', '12,50', '25,00', 'scope="col"', 'scope="row"', 'tabindex="0"']) assert.ok(html.includes(texto), texto);
  assert.ok(!html.includes('Adicionar produto'));
});
