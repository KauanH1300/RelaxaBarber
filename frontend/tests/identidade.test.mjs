import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';
const { estabelecimento, software, assinaturaSoftware } = await carregarTs('config/identidade.ts');
const { AcessoCliente, InicioCliente } = await carregarTs('pages/portal/PortalCliente.tsx');
const { MeusAgendamentos } = await carregarTs('pages/portal/MeusAgendamentos.tsx');
const { CabecalhoPublico, RodapePublico } = await carregarTs('pages/publico/ComponentesPublicos.tsx');
const render = component => renderToStaticMarkup(createElement(MemoryRouter, {initialEntries:['/cliente/cadastro?retorno=agendamento']}, component));

test('software e estabelecimento possuem identidades separadas', () => {
  assert.equal(software.nome, 'RelaxaBarber');
  assert.equal(estabelecimento.nome, 'Barbearia Relaxa o Bigode');
  assert.equal(assinaturaSoftware, 'Powered by RelaxaBarber');
});
for (const modo of ['entrar','cadastro','recuperar','ativar','redefinir']) test(`conta do estabelecimento e retorno preservados: ${modo}`, () => {
  const html = render(createElement(AcessoCliente, {modo}));
  assert.ok(html.includes(estabelecimento.nome));
  assert.ok(html.includes(assinaturaSoftware));
  assert.ok(html.includes('<img'));
  assert.ok(!html.includes('Seu espaço na RelaxaBarber'));
  assert.ok(html.includes('/cliente/entrar?retorno=agendamento'));
});
for (const component of [InicioCliente,MeusAgendamentos,CabecalhoPublico,RodapePublico]) test(`marca da barbearia: ${component.name}`, () => {
  const html = render(createElement(component));
  assert.ok(html.includes(estabelecimento.nome));
  assert.ok(html.includes(assinaturaSoftware));
  assert.ok(html.includes('<img'));
  assert.ok(!html.includes('RelaxaBarber · Clientes'));
});
