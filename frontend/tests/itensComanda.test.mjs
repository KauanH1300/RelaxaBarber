import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';
const map = new Map();
globalThis.localStorage = { getItem: () => null, removeItem() {} };
globalThis.window = new EventTarget();
globalThis.sessionStorage = { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), removeItem: (k) => map.delete(k) };
const s = await carregarTs('services/itensComanda.ts');
const { ItensComanda } = await carregarTs('pages/comandas/ComponentesComanda.tsx');
const { AdicionarServico } = await carregarTs('pages/comandas/AdicionarServico.tsx');
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

function renderizar(comanda = c, usuario = { id: 'barbeiro', perfil: 'admin' }, bloqueado = false, motivoBloqueio) {
  return renderToStaticMarkup(createElement(MemoryRouter, null, createElement(Routes, null,
    createElement(Route, { element: createElement(Outlet, { context: { usuario } }) },
      createElement(Route, { index: true, element: createElement(AdicionarServico, {
        comanda, bloqueado, motivoBloqueio, aoBloqueio() {}, aoAtualizar() {},
      }) })))));
}

for (const [nome, mudanca, mensagem] of [
  ['operacionalmente fechada', { status: 'fechada' }, 'Comanda operacionalmente fechada'],
  ['financeiramente fechada', { status: 'fechada', status_apresentacao: 'fechada' }, 'Comanda financeiramente fechada'],
  ['financeiro não verificado', { status_apresentacao: 'nao_verificado' }, 'Classificação financeira não verificada'],
  ['classificação ausente', { status_apresentacao: undefined }, 'Classificação financeira não verificada'],
  ['cancelada', { status: 'cancelada' }, 'Comanda ou atendimento cancelado'],
  ['reserva pendente', { status: 'pendente' }, 'Comanda ainda pendente de abertura'],
]) {
  test(`inclusão indisponível explica ${nome} sem habilitar ação`, () => {
    const html = renderizar({ ...c, ...mudanca });
    assert.ok(html.includes(mensagem));
    assert.ok(html.includes('role="status"'));
    assert.ok(!html.includes('>Adicionar serviço</button>'));
    assert.equal(s.permiteInclusao({ id: 'barbeiro', perfil: 'admin' }, { ...c, ...mudanca }), false);
  });
}

test('mensagem sem permissão não revela classificação financeira de terceiros', () => {
  for (const status_apresentacao of ['fechada', 'nao_verificado', 'pagamento_pendente']) {
    const html = renderizar({ ...c, status_apresentacao }, { id: 'outro', perfil: 'barbeiro_chefe' });
    assert.ok(html.includes('Seu perfil não tem permissão'));
    assert.ok(!html.includes('Comanda financeiramente fechada'));
    assert.ok(!html.includes('Classificação financeira não verificada'));
    assert.ok(!html.includes('>Adicionar serviço</button>'));
  }
});

test('concluído e pagamento pendente explicam que a inclusão continua disponível', () => {
  const html = renderizar();
  assert.ok(html.includes('Atendimento concluído não significa fechamento financeiro'));
  assert.ok(html.includes('Pagamento pendente. Adicionar um serviço atualiza o total'));
  assert.ok(html.includes('>Adicionar serviço</button>'));
  assert.ok(!html.includes('disabled=""'));
});

test('aguardando fechamento mantém ação e explica possível novo saldo', () => {
  const html = renderizar({ ...c, status_apresentacao: 'aguardando_fechamento' });
  assert.ok(html.includes('Quitação verificada, aguardando fechamento'));
  assert.ok(html.includes('>Adicionar serviço</button>'));
});

test('coordenação financeira desabilita botão visível e explica bloqueio', () => {
  const html = renderizar(c, { id: 'barbeiro', perfil: 'admin' }, true);
  assert.ok(html.includes('disabled=""'));
  assert.ok(html.includes('>Adicionar serviço</button>'));
  assert.ok(html.includes('Resolva a consulta ou confirmação financeira'));
});

test('motivo financeiro específico é exibido sem substituir a elegibilidade', () => {
  for (const motivo of [
    'Aguarde a consulta financeira antes de adicionar serviços.',
    'Há uma operação financeira aguardando confirmação. Recupere a operação original antes de adicionar serviços.',
    'Conclua ou cancele a revisão da operação financeira antes de adicionar serviços.',
  ]) {
    const html = renderizar(c, { id: 'barbeiro', perfil: 'admin' }, true, motivo);
    assert.ok(html.includes(motivo));
    assert.ok(html.includes('disabled=""'));
    assert.ok(html.includes('>Adicionar serviço</button>'));
  }
});

test('inclusão pendente substitui nova inclusão por recuperação original', () => {
  const key = s.chaveInclusao('barbeiro', c);
  s.salvarInclusao(key, p);
  try {
    const html = renderizar();
    assert.ok(html.includes('Inclusão aguardando confirmação'));
    assert.ok(html.includes('>Recuperar inclusão</button>'));
    assert.ok(!html.includes('>Adicionar serviço</button>'));
  } finally { s.limparInclusao(key, p); }
});
