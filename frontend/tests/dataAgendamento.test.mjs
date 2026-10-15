import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const apiStub = 'data:text/javascript,' + encodeURIComponent('export default { get() { throw new Error("Rede proibida neste teste"); } };');
let source = await readFile(new URL('../src/pages/agendamentos/NovoAgendamentoModal.tsx', import.meta.url), 'utf8');
let { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023, jsx: ts.JsxEmit.ReactJSX },
});
outputText = outputText.replace(/from ["']\.\.\/\.\.\/services\/api["']/g, `from '${apiStub}'`);
outputText = outputText.replace(/from ["'](react(?:\/jsx-runtime)?|axios)["']/g, (_, specifier) => `from '${import.meta.resolve(specifier)}'`);
const { NovoAgendamentoModal } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
function render(date, open = true) {
  return renderToStaticMarkup(createElement(NovoAgendamentoModal, {
    aberto: open, dataInicial: date, barbeiros: [], onFechar() {}, onSalvo() {},
  }));
}

test('modal recebe a data escolhida na agenda, inclusive em outro mês/ano', () => {
  for (const date of ['2030-05-02', '2030-12-31', '2031-01-01']) {
    assert.match(render(date), new RegExp(`type="date" value="${date}"`));
  }
});

test('nova montagem usa o novo dia em vez da data anterior', () => {
  assert.match(render('2030-05-02'), /type="date" value="2030-05-02"/);
  assert.equal(render('2030-05-02', false), '');
  assert.match(render('2030-05-03'), /type="date" value="2030-05-03"/);
});
