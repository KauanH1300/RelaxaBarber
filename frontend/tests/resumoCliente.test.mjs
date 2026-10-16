import assert from 'node:assert/strict';
import test from 'node:test';
import { carregarTs } from './helpers/carregarTs.mjs';
const { descricaoEscopo } = await carregarTs('services/resumoCliente.ts');

test('rótulo de consolidado da empresa exige escopo completo', () => {
  assert.match(descricaoEscopo({ escopo_filiais: 'empresa', escopo_profissional: 'todos', parcial: false }), /Consolidado da RelaxaBarber/);
  assert.match(descricaoEscopo({ escopo_filiais: 'filiais_autorizadas', escopo_profissional: 'todos', parcial: true }), /Resumo parcial/);
  assert.match(descricaoEscopo({ escopo_filiais: 'empresa', escopo_profissional: 'todos', parcial: true }), /Resumo parcial/);
  assert.match(descricaoEscopo({ escopo_filiais: 'filiais_autorizadas', escopo_profissional: 'proprio', parcial: true }), /somente seus atendimentos/);
});
