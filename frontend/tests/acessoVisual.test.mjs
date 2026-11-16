import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';
const { Login }=await carregarTs('pages/auth/Login.tsx');
const { AcessoCliente }=await carregarTs('pages/portal/PortalCliente.tsx');
const render=(component)=>renderToStaticMarkup(createElement(MemoryRouter,{initialEntries:['/login?retorno=agendamento']},component));

for(const equipe of [false,true])test(`layout compartilhado, controles acessiveis e contexto preservado: ${equipe?'equipe':'cliente'}`,()=>{
  const html=render(equipe?createElement(Login):createElement(AcessoCliente,{modo:'entrar'}));
  assert.ok(html.includes('class="acesso-card"'));assert.ok(html.includes('Bem-vindo de volta'));
  assert.ok(html.includes('Barbearia Relaxa o Bigode'));assert.ok(html.includes('Tipo de acesso'));
  assert.ok(html.includes('href="/cliente/entrar?retorno=agendamento"'));
  assert.ok(html.includes('href="/login?retorno=agendamento"'));
  const ativo=html.match(/<a[^>]*aria-current="page"[^>]*>/)?.[0];
  assert.ok(ativo?.includes(`href="${equipe?'/login':'/cliente/entrar'}?retorno=agendamento"`));
  assert.ok(html.includes('for="acesso-email"'));assert.ok(html.includes('autoComplete="current-password"'));
  assert.ok(html.includes('aria-label="Mostrar senha"'));assert.ok(!html.includes('30 dias'));
  assert.ok(!html.includes('CPF'));assert.ok(!html.includes('type="checkbox"'));
  if(equipe){assert.ok(!html.includes('/cliente/cadastro'));assert.ok(!html.includes('/cliente/recuperar'));assert.ok(html.includes('Cadastro pela administração'));}
  else {assert.ok(html.includes('/cliente/cadastro?retorno=agendamento'));assert.ok(html.includes('/cliente/recuperar?retorno=agendamento'));assert.ok(html.includes('/agendar?etapa=horario'));}
});
