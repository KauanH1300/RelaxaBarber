import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const { carregarTs } = await import('./helpers/carregarTs.mjs');
const { NovoAgendamentoModal } = await carregarTs('pages/agendamentos/NovoAgendamentoModal.tsx');
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
