// Executor offline para a imagem Docker local. O checkout em /source é somente leitura.
const fs = require('node:fs');
const cp = require('node:child_process');
for (const nome of fs.readdirSync('/source')) {
  if (nome === 'src' || nome === 'tests' || /^(package\.json|tsconfig.*json|vite\.config.*|eslint\.config.*|index\.html)$/.test(nome)) {
    fs.cpSync(`/source/${nome}`, `/app/${nome}`, { recursive: true });
  }
}
const testes = fs.readdirSync('/app/tests').filter((nome) => nome.endsWith('.test.mjs')).map((nome) => `tests/${nome}`);
const comandos = process.argv.includes('--browser') ? [
  ['--experimental-websocket', 'tests/comandas.browser.mjs'],
  ['--experimental-websocket', 'tests/financeiro.browser.mjs'],
] : [
  ['--test', '--test-reporter=dot', ...testes],
  ['node_modules/typescript/bin/tsc', '-b'],
  ['node_modules/vite/bin/vite.js', 'build'],
  ['node_modules/eslint/bin/eslint.js', '.'],
];
for (const argumentos of comandos) {
  if (process.argv.includes('--financeiro-only') && argumentos.includes('tests/comandas.browser.mjs')) continue;
  const resultado = cp.spawnSync(process.execPath, argumentos, { cwd: '/app', stdio: 'inherit' });
  process.stdout.write(`CHECK ${argumentos[0]} EXIT ${resultado.status}\n`);
  if (resultado.status) process.exitCode = 1;
}
