import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';

const p=await carregarTs('services/agendamentoPublico.ts');
const {InicioPublico}=await carregarTs('pages/publico/InicioPublico.tsx');
const {AgendamentoPublico}=await carregarTs('pages/publico/AgendamentoPublico.tsx');
const {AcessoCliente}=await carregarTs('pages/portal/PortalCliente.tsx');
function storage(){const map=new Map();globalThis.sessionStorage={getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v)};return map;}
const draft={servico:'servico-real',barbeiro:'Rodrigo Relaxa',data:'2099-05-20',hora:'13:45'};

test('catalogo existente publico usa GET sem token, cookie ou filial e exclui inativos',async()=>{
  let request;
  p.apiPublica.defaults.adapter=async config=>{request=config;return {status:200,data:[{id:'s1',nome:'Corte',preco:40,tempo_estimado:30,ativo:true},{id:'s2',nome:'Inativo',preco:10,tempo_estimado:10,ativo:false}],config};};
  assert.equal((await p.catalogoPublico()).length,1);
  assert.equal(request.url,'/servicos/');assert.equal(request.method,'get');assert.equal(request.withCredentials,false);
  assert.equal(request.headers.Authorization,undefined);assert.equal(request.params,undefined);
});

test('preferencias sobrevivem ao retorno de autenticacao sem armazenar dados pessoais',()=>{
  const map=storage();assert.equal(p.guardarEscolhas({...draft,senha:'segredo',email:'pessoa@example.com',token:'privado'}),true);
  assert.deepEqual(p.lerEscolhas(),draft);
  const saved=[...map.values()][0];assert.ok(!saved.includes('segredo'));assert.ok(!saved.includes('pessoa@'));assert.ok(!saved.includes('privado'));
});

test('dados invalidos, expirados e falha de armazenamento nao quebram a pagina',()=>{
  const map=storage();map.set('rb_agendamento_publico_v1','{invalido');assert.deepEqual(p.lerEscolhas(),p.escolhasVazias);
  map.set('rb_agendamento_publico_v1',JSON.stringify({expira:Date.now()-1,escolhas:draft}));assert.deepEqual(p.lerEscolhas(),p.escolhasVazias);
  assert.equal(p.guardarEscolhas({...draft,barbeiro:'id-administrativo-forjado'}),false);
  assert.equal(p.guardarEscolhas({...draft,hora:'99:99'}),false);
  globalThis.sessionStorage={getItem:()=>{throw Error('bloqueado');},setItem:()=>{throw Error('bloqueado');}};
  assert.deepEqual(p.lerEscolhas(),p.escolhasVazias);assert.equal(p.guardarEscolhas(draft),false);
});

test('retorno aceita somente destino interno fixo e mantem login normal inalterado',()=>{
  assert.equal(p.destinoAposLogin('?retorno=agendamento'),'/agendar?etapa=confirmacao');
  assert.equal(p.destinoAposLogin('?retorno=https://hostil.example'),'/cliente');
  assert.equal(p.destinoAposLogin('?retorno=//hostil.example'),'/cliente');
  assert.equal(p.destinoAposLogin(''),'/cliente');
  assert.equal(p.sufixoRetorno('?retorno=agendamento'),'?retorno=agendamento');
});

test('inicio tem apresentacao, servicos, equipe e acesso secundario separado para funcionarios',()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(InicioPublico)));
  assert.ok(html.includes('Seu estilo.'));assert.ok(html.includes('id="servicos"'));assert.ok(html.includes('id="equipe"'));
  assert.ok(html.includes('href="/agendar"'));assert.ok(html.includes('Área dos funcionários'));assert.ok(html.includes('href="/login"'));
  assert.ok(html.includes('reserva online está em preparação'));assert.ok(!html.includes('R$'));
});

test('agendamento publico apresenta as cinco etapas sem exigir login no inicio',()=>{
  storage();const html=renderToStaticMarkup(createElement(MemoryRouter,{initialEntries:['/agendar']},createElement(AgendamentoPublico)));
  for(const label of ['Serviço','Barbeiro','Data e horário','Seu acesso','Confirmação'])assert.ok(html.includes(label));
  assert.ok(html.includes('Escolha seu serviço'));assert.ok(!html.includes('Entrar para revisar'));assert.ok(html.includes('ainda não reservam'));
});

for(const modo of ['entrar','cadastro','recuperar','ativar','redefinir'])test(`autenticacao ${modo} preserva contexto e oferece retorno as escolhas`,()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,{initialEntries:[`/cliente/${modo}?retorno=agendamento`]},createElement(AcessoCliente,{modo})));
  assert.ok(html.includes('/cliente/entrar?retorno=agendamento'));assert.ok(html.includes('/cliente/cadastro?retorno=agendamento'));
  assert.ok(html.includes('/cliente/recuperar?retorno=agendamento'));assert.ok(html.includes('/agendar?etapa=horario'));
});
