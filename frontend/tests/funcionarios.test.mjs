import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Outlet, Routes, Route } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';

globalThis.localStorage = { getItem: () => null };
globalThis.window = new EventTarget();
const service = await carregarTs('services/funcionarios.ts');
const { FormFuncionario, Funcionarios } = await carregarTs('pages/funcionarios/Funcionarios.tsx');
const api = (await carregarTs('services/api.ts')).default;
const filial = { id: 'filial', nome: 'Unidade de teste', fuso_horario: 'America/Recife' };
const funcionario = { id: 'pessoa', nome: 'Pessoa teste', email: 'pessoa@example.com', telefone: null, perfil: 'barbeiro', ativo: true };
const { EditorRestricoes }=await carregarTs('pages/funcionarios/RestricoesServicos.tsx');

test('editor explica todos por padrao e nao permite salvar antes da consulta',()=>{
  const html=renderToStaticMarkup(createElement(EditorRestricoes,{filialId:'filial',barbeiroId:'barbeiro'}));
  for(const texto of ['Serviços que não realiza','Nenhuma seleção','incluindo novos serviços','filial selecionada'])assert.ok(html.includes(texto));
  assert.ok(!html.includes('<form'));assert.ok(html.includes('Aguardando consulta'));
});
test('contrato de excecoes explicitas e isolado por filial e barbeiro',async()=>{
  const calls=[];api.defaults.adapter=async config=>{calls.push(config);return {status:200,data:{servicos:[],restricoes:[]},config};};
  await service.consultarRestricoesServicos('filial','barbeiro');
  await service.salvarRestricoesServicos('filial','barbeiro',['corte']);
  await service.salvarRestricoesServicos('outra','barbeiro',[]);
  assert.equal(calls[0].url,'/filiais/filial/barbeiros/barbeiro/restricoes-servicos');
  assert.deepEqual(JSON.parse(calls[1].data),{servicos:['corte']});
  assert.equal(calls[2].url,'/filiais/outra/barbeiros/barbeiro/restricoes-servicos');
  assert.deepEqual(JSON.parse(calls[2].data),{servicos:[]});
});

test('admin é o único perfil administrativo de funcionários', () => {
  for (const perfil of ['admin', 'recepcao', 'barbeiro', 'barbeiro_chefe']) assert.equal(service.podeGerenciarFuncionarios({ perfil }), perfil === 'admin');
});
test('formulário de cadastro tem quatro perfis, senha inicial e filiais explícitas', () => {
  const html = renderToStaticMarkup(createElement(FormFuncionario, { filiais: [filial], proprio: false, aoSalvar() {}, aoCancelar() {} }));
  for (const texto of ['Nome', 'E-mail', 'Telefone', 'Senha inicial', 'new-password', 'Unidade de teste', 'value="admin"', 'value="recepcao"', 'value="barbeiro"', 'value="barbeiro_chefe"']) assert.ok(html.includes(texto), texto);
  assert.ok(!html.includes('Excluir funcionário'));
});
test('edição preserva senha e protege próprio administrador', () => {
  const html = renderToStaticMarkup(createElement(FormFuncionario, { funcionario: { ...funcionario, perfil: 'admin' }, filiais: [filial], proprio: true, aoSalvar() {}, aoCancelar() {} }));
  assert.ok(!html.includes('type="password"'));
  assert.match(html, /select disabled=""/);
  assert.match(html, /type="checkbox" disabled=""/);
  assert.ok(html.includes('Funcionário ativo'));
});
test('rota administrativa nega perfis sem permissão antes de consultar filiais', () => {
  for (const perfil of ['recepcao', 'barbeiro', 'barbeiro_chefe']) {
    const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Routes, null,
      createElement(Route, { element: createElement(Outlet, { context: { usuario: { ...funcionario, perfil } } }) },
        createElement(Route, { index: true, element: createElement(Funcionarios) })))));
    assert.ok(html.includes('Somente administradores'));
    assert.ok(!html.includes(funcionario.email));
  }
});
test('contratos de cadastro, edição e vínculos usam APIs reais sem campos privados', async () => {
  const calls = [];
  api.defaults.adapter = async config => { calls.push(config); return { data: [], status: 200, statusText: 'OK', headers: {}, config }; };
  const dados = { nome: 'Pessoa', email: 'pessoa@example.com', telefone: null, perfil: 'recepcao', ativo: true };
  await service.listarFuncionarios(); await service.cadastrarFuncionario(dados, 'senha-ficticia', ['filial']);
  await service.atualizarFuncionario('pessoa', dados); await service.listarVinculos('filial'); await service.definirVinculo('filial', 'pessoa', false);
  assert.deepEqual(calls.map(c => [c.method, c.url]), [['get','/usuarios'],['post','/usuarios'],['patch','/usuarios/pessoa'],['get','/filiais/filial/usuarios'],['put','/filiais/filial/usuarios/pessoa']]);
  assert.deepEqual(JSON.parse(calls[1].data).filial_ids, ['filial']);
  assert.ok(!('ativo' in JSON.parse(calls[1].data)));
  assert.ok(!('senha' in JSON.parse(calls[2].data)));
  assert.deepEqual(JSON.parse(calls[4].data), { ativo: false });
});
