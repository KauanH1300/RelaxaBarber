import { readFile, access } from 'node:fs/promises';
import ts from 'typescript';

// Executa os módulos reais com dependências já instaladas. Sem build ou rede.
const cache = new Map();
export async function moduloTs(url) {
  const key = url.href;
  if (cache.has(key)) return cache.get(key);
  let source = await readFile(url, 'utf8');
  source = source.replace(/import\.meta\.env\.VITE_API_URL/g, "'http://api-teste.invalid'");
  let { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023, jsx: ts.JsxEmit.ReactJSX },
  });
  outputText = outputText.replace(/import\s*['"][^'"]+\.css['"];?/g, '');
  const imports = [...outputText.matchAll(/from\s*['"]([^'"]+)['"]/g)];
  for (const match of imports) {
    const specifier = match[1];
    let resolved;
    if (specifier.startsWith('.')) {
      const target = new URL(specifier, url);
      if (/\.(png|svg)$/.test(target.pathname)) resolved = 'data:text/javascript,export default ""';
      else {
        let file;
        for (const extension of ['.ts', '.tsx']) {
          const candidate = new URL(target.href + extension);
          try { await access(candidate); file = candidate; break; } catch { /* próxima extensão */ }
        }
        if (!file) throw new Error(`Módulo de teste não encontrado: ${specifier}`);
        resolved = await moduloTs(file);
      }
    } else resolved = import.meta.resolve(specifier);
    outputText = outputText.replaceAll(`'${specifier}'`, JSON.stringify(resolved)).replaceAll(`"${specifier}"`, JSON.stringify(resolved));
  }
  const result = `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`;
  cache.set(key, result);
  return result;
}
export async function carregarTs(relative) {
  return import(await moduloTs(new URL(relative, new URL('../../src/', import.meta.url))));
}
