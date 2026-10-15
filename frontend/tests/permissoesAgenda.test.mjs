import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

// Usa o TypeScript já instalado; sem novas dependências ou arquivos de build.
const source = await readFile(new URL('../src/services/permissoesAgenda.ts', import.meta.url), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023 },
});
const { podeOperarAgenda, profissionaisParaCriacao } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
);
const profissionais = [{ id: 'proprio', nome: 'Ana' }, { id: 'outro', nome: 'Beto' }];

for (const perfil of ['admin', 'recepcao', 'barbeiro_chefe', 'barbeiro']) {
  for (const profissional of profissionais) {
    test(`${perfil}: ações sobre ${profissional.id}`, () => {
      assert.equal(
        podeOperarAgenda({ id: 'proprio', perfil }, profissional.id),
        ['admin', 'recepcao'].includes(perfil) || profissional.id === 'proprio',
      );
    });
  }
  test(`${perfil}: seleção de criação`, () => {
    assert.deepEqual(
      profissionaisParaCriacao({ id: 'proprio', perfil }, profissionais),
      ['admin', 'recepcao'].includes(perfil) ? profissionais : profissionais.slice(0, 1),
    );
  });
}

test('sem sessão ou perfil desconhecido não libera ações', () => {
  assert.equal(podeOperarAgenda(null, 'proprio'), false);
  assert.deepEqual(profissionaisParaCriacao(null, profissionais), []);
  assert.equal(podeOperarAgenda({ id: 'proprio', perfil: 'desconhecido' }, 'proprio'), false);
});
