/** Estende a homologação real existente sem alterar suas garantias financeiras.
 * Requer o PostgreSQL descartável já provisionado; não prepara schema/migrações.
 */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

async function validarLayout({ command, context, evaluate, record, writeFile, assert, modo = 'real' }) {
  const key = async (value, shift = false) => {
    const actions = [...(shift ? [{ type: 'keyDown', value: '\uE008' }] : []),
      { type: 'keyDown', value }, { type: 'keyUp', value },
      ...(shift ? [{ type: 'keyUp', value: '\uE008' }] : [])];
    await command('input.performActions', { context, actions: [{ type: 'key', id: 'layout-keyboard', actions }] });
  };
  // A suíte base usa click() programático, que não foca o acionador. Reabrir
  // por teclado estabelece o foco real que o diálogo deve restaurar.
  await evaluate('document.querySelector("dialog>header button").click()');
  for (let i = 0; i < 100 && await evaluate('!!document.querySelector("dialog")'); i++) await new Promise((resolve) => setTimeout(resolve, 50));
  await evaluate('document.querySelector(".comanda-card footer button").focus()');
  await key('\uE007');
  for (let i = 0; i < 100; i++) {
    if (await evaluate('document.querySelector(".comanda-financeiro")?.getAttribute("aria-busy")==="false"')) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  for (const [name, width, height] of [['desktop', 1440, 1100], ['tablet', 900, 1000], ['celular', 390, 844], ['celular-estreito', 320, 740]]) {
    await command('browsingContext.setViewport', { context, viewport: { width, height } });
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'), `${name}: página sem overflow`);
    assert.ok(await evaluate('document.querySelector("dialog").scrollWidth<=document.querySelector("dialog").clientWidth'), `${name}: modal sem overflow`);
    await evaluate('document.querySelector("dialog").scrollTop=0');
    let shot = await command('browsingContext.captureScreenshot', { context });
    await writeFile(`/evidencias/detalhe-${modo}-${name}.png`, Buffer.from(shot.data, 'base64'));
    await evaluate('document.querySelector(".financeiro-resumo").scrollIntoView({block:"start"})');
    assert.ok(await evaluate(`(()=>{const summary=document.querySelector('.financeiro-resumo').getBoundingClientRect();const header=document.querySelector('dialog>header').getBoundingClientRect();return summary.top>=header.bottom && summary.bottom<=innerHeight})()`), `${name}: valores visíveis abaixo do cabeçalho`);
    shot = await command('browsingContext.captureScreenshot', { context });
    await writeFile(`/evidencias/financeiro-${modo}-${name}.png`, Buffer.from(shot.data, 'base64'));
    const selector = 'form[data-operacao="fechamento-financeiro"] input[inputmode="decimal"]';
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'center'})`);
    assert.ok(await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)}),r=e.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===e})()`), `${name}: campo não encoberto`);
    await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);
    await key('\uE004');
    assert.ok(await evaluate('!!document.activeElement.closest("dialog")'), `${name}: Tab dentro do modal`);
    await evaluate('document.querySelector(".financeiro-historico-area").open=true');
    await evaluate('document.querySelector(".financeiro-historico-area").scrollIntoView({block:"center"})');
    shot = await command('browsingContext.captureScreenshot', { context });
    await writeFile(`/evidencias/historico-${modo}-${name}.png`, Buffer.from(shot.data, 'base64'));
    await evaluate('document.querySelector(".financeiro-historico-area").open=false;document.querySelector("dialog>header button").focus()');
    await key('\uE004', true);
    assert.ok(await evaluate('!!document.activeElement.closest("dialog")'), `${name}: Shift+Tab contido`);
    const previousFocus = await evaluate('document.activeElement.outerHTML.slice(0,250)');
    await key('\uE004');
    assert.ok(await evaluate('document.activeElement.matches("dialog>header button")'), `${name}: ciclo do foco, anterior=${previousFocus}, atual=${await evaluate('document.activeElement.outerHTML.slice(0,250)')}`);
    await key('\uE00C');
    for (let i = 0; i < 100 && await evaluate('!!document.querySelector("dialog")'); i++) await new Promise((resolve) => setTimeout(resolve, 50));
    assert.ok(await evaluate('!document.querySelector("dialog") && document.activeElement.matches(".comanda-card footer button")'), `${name}: Escape e foco restaurado`);
    shot = await command('browsingContext.captureScreenshot', { context });
    await writeFile(`/evidencias/listagem-${modo}-${name}.png`, Buffer.from(shot.data, 'base64'));
    await key('\uE007');
    let ready = false;
    for (let i = 0; i < 100; i++) {
      ready = await evaluate('document.querySelector(".comanda-financeiro")?.getAttribute("aria-busy")==="false"');
      if (ready) break;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert.ok(ready, `${name}: Enter abre detalhes`);
    await record(`layout ${modo} ${name}: rolagem, valores, campo sem sobreposição, histórico, Tab/Shift+Tab/Escape/Enter`, { width, height });
  }
  await command('browsingContext.setViewport', { context, viewport: { width: 1440, height: 1100 } });
}

const simulated = process.argv.includes('--layout-simulado');
const original = new URL(simulated ? './financeiro.browser.mjs' : './homologacao-etapa3.browser.mjs', import.meta.url);
let source = (await readFile(original, 'utf8')).replaceAll('import.meta.url', JSON.stringify(original.href));
if (simulated) {
  const marker = "  await waitText('Valor Total'); await waitText('Valor Recebido');";
  assert.equal(source.split(marker).length, 2);
  source = source.replace(marker, `${marker}\n await (${validarLayout.toString()})({command,context,evaluate,record:async(c,d)=>console.log('PASS',c,JSON.stringify(d)),writeFile,assert,modo:'simulado'});`);
} else {
const marker = "  await open(c); await parcel(1, '100.00');";
assert.equal(source.split(marker).length, 2, 'ponto de extensão único na suíte homologada');
source = source.replace(marker, `  await open(c);\n  await (${validarLayout.toString()})({command,context,evaluate,record,writeFile,assert});\n  await parcel(1, '100.00');`);
const summaryMarker = "  const original = calls.at(-1);";
assert.equal(source.split(summaryMarker).length, 2);
source = source.replace(summaryMarker, `  assert.ok(await evaluate('document.querySelector(".financeiro-resumo").textContent.includes("300,00")'));
  assert.equal(await evaluate('document.querySelector(".financeiro-resumo>div:nth-child(2) dd").textContent.replaceAll(String.fromCharCode(160), "").replaceAll(" ", "")'), 'R$300,00');
${summaryMarker}`);
const unavailableMarker = "failNext = true; await confirm(); await waitText('Operação aguardando confirmação');";
assert.equal(source.split(unavailableMarker).length, 2);
source = source.replace(unavailableMarker, `const beforeUnavailable = calls.length; ${unavailableMarker}
  await waitFor(() => calls.length > beforeUnavailable, '503 capturado no proxy');
  await waitFor(() => evaluate('document.querySelector(".comanda-financeiro")?.getAttribute("aria-busy")==="false"'), '503 e consulta concluídos antes de guardar a chave');`);
}
try { await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`); }
catch (error) { console.error('FAIL homologação Etapa 4:', error.message); process.exitCode = 1; }
