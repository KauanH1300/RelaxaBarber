import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';
globalThis.localStorage={getItem:()=> 'token-funcionario-nao-enviar'};
globalThis.window=new EventTarget();
const p=await carregarTs('services/portalCliente.ts');
const {AcessoCliente,InicioCliente}=await carregarTs('pages/portal/PortalCliente.tsx');
const {TrocaEmailCliente}=await carregarTs('pages/portal/TrocaEmailCliente.tsx');

test('troca de email confirma os dois contatos sem senha ou identidade de funcionario',async()=>{
  const calls=[];
  p.apiPortal.defaults.adapter=async config=>{calls.push(config);return {status:200,data:{},config};};
  await p.solicitarTrocaEmail('novo@example.com');
  await p.confirmarTrocaEmail('atual','pedido','123456');
  await p.confirmarTrocaEmail('novo','pedido','654321');
  assert.deepEqual(calls.map(c=>c.url),['/portal-clientes/troca-email','/portal-clientes/troca-email/confirmar-atual','/portal-clientes/troca-email/confirmar-novo']);
  assert.deepEqual(JSON.parse(calls[0].data),{email_novo:'novo@example.com'});
  for(const c of calls){assert.equal(c.withCredentials,true);assert.equal(c.headers.Authorization,undefined);assert.ok(!c.data.includes('senha'));}
});

test('troca aguarda sessao e orienta recuperacao antes do login sem mostrar dados',()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(TrocaEmailCliente)));
  assert.ok(html.includes('Validando seu acesso'));assert.ok(!html.includes('<form'));
  assert.ok(html.includes('login realizado nos últimos dez minutos'));
  assert.ok(html.includes('/cliente/recuperar'));assert.ok(!html.includes('type="password"'));
});

test('portal usa cookie e nunca envia token ou filial de funcionário',async()=>{
  const calls=[];
  p.apiPortal.defaults.adapter=async config=>{calls.push(config);return {status:200,data:{},config};};
  await p.entrarCliente('cliente@example.com','senha-ficticia');await p.perfilCliente();await p.sairCliente();
  assert.deepEqual(calls.map(c=>c.url),['/portal-clientes/login','/portal-clientes/me','/portal-clientes/logout']);
  for(const c of calls){assert.equal(c.withCredentials,true);assert.equal(c.headers.Authorization,undefined);assert.equal(c.params,undefined);}
});

test('cadastro, confirmação e redefinição enviam somente dados do fluxo',async()=>{
  const calls=[];p.apiPortal.defaults.adapter=async config=>{calls.push({url:config.url,data:JSON.parse(config.data)});return {status:202,data:{solicitacao_id:'pedido',mensagem:'generica'},config};};
  await p.cadastrarConta({nome:'Cliente',telefone:'11999991234',email:'cliente@example.com',senha:'senha-ficticia'});
  await p.recuperarConta('cliente@example.com');await p.confirmarConta('pedido','123456');await p.redefinirSenhaCliente('pedido','123456','nova-senha-ficticia');
  assert.deepEqual(calls[1].data,{email:'cliente@example.com'});
  assert.deepEqual(calls[2].data,{solicitacao_id:'pedido',codigo:'123456'});
  assert.equal(calls[3].url,'/portal-clientes/redefinir');
});

for(const modo of ['entrar','cadastro','recuperar','ativar','redefinir'])test(`formulário acessível do cliente: ${modo}`,()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(AcessoCliente,{modo})));
  assert.ok(html.includes('RelaxaBarber · Clientes'));assert.ok(html.includes('Acesso da equipe'));assert.ok(html.includes('<form'));
  if(['cadastro','redefinir'].includes(modo)){assert.ok(html.includes('minLength="12"'));assert.ok(html.includes('new-password'));}
  if(['ativar','redefinir'].includes(modo)){assert.ok(html.includes('one-time-code'));assert.ok(html.includes('seis dígitos'));}
});

test('área protegida aguarda validação antes de mostrar dados pessoais',()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(InicioCliente)));
  assert.ok(html.includes('Validando seu acesso'));assert.ok(!html.includes('E-mail confirmado'));assert.ok(!html.includes('token-funcionario'));
});

test('acesso publico orienta recuperar senha e nao oferece troca de email sem login',()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(AcessoCliente,{modo:'entrar'})));
  assert.ok(html.includes('/cliente/recuperar'));assert.ok(!html.includes('/cliente/trocar-email'));
});
