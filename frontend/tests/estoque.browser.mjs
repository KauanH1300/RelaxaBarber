import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)); const profile=await mkdtemp(join(tmpdir(),'estoque-browser-'));
const filial='10000000-0000-4000-8000-000000000001', usuario='20000000-0000-4000-8000-000000000001';
let produtos=Array.from({length:10},(_,i)=>({id:String(i+1),nome:`Item ${i+1}`,unidade:'un',venda:true,consumo:i===0,custo:'2.00',preco_venda:'5.00',estoque_minimo:'2.000',saldo:i===0?'0.000':'5.000',ativo:true}));
let movimentos=[];const chamadas=[];let perfil='admin';const catalogos={categorias:[],marcas:[]};
const server=createServer(async(req,res)=>{
 res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Headers','Authorization, Content-Type, Idempotency-Key');res.setHeader('Access-Control-Allow-Methods','GET, POST, PUT, OPTIONS');if(req.method==='OPTIONS')return res.writeHead(204).end();
 const url=new URL(req.url,'http://localhost');let raw='';for await(const chunk of req)raw+=chunk;const body=raw?JSON.parse(raw):null;chamadas.push([req.method,url.pathname,url.searchParams.get('filial_id')]);
 const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
 if(url.pathname==='/auth/me')return reply(200,{id:usuario,nome:'Teste',email:'teste@example.test',perfil,ativo:true});
 if(url.pathname==='/filiais')return reply(200,[{id:filial,nome:'Unidade teste',fuso_horario:'America/Recife'}]);
 const catalogo=url.pathname.match(/^\/estoque\/catalogos\/(categorias|marcas)$/);
 if(catalogo && req.method==='GET')return reply(200,catalogos[catalogo[1]]);
 if(catalogo && req.method==='POST'){const item={id:`${catalogo[1]}-${catalogos[catalogo[1]].length}`,nome:body.nome};catalogos[catalogo[1]].push(item);return reply(201,item);}
 if(url.pathname==='/estoque/produtos' && req.method==='GET')return reply(200,produtos);
 if(url.pathname==='/estoque/produtos' && req.method==='POST'){const p={...body,id:'novo',saldo:'0.000',filial_id:filial};produtos=[p,...produtos];return reply(201,p);}
 if(url.pathname==='/estoque/produtos/novo' && req.method==='PUT'){const p=produtos.find(p=>p.id==='novo');Object.assign(p,body);return reply(200,p);}
 if(url.pathname==='/estoque/produtos/novo/movimentos' && req.method==='GET')return reply(200,movimentos);
 if(url.pathname==='/estoque/produtos/novo/movimentos' && req.method==='POST'){const p=produtos.find(p=>p.id==='novo');const delta=body.tipo==='baixa'?-Number(body.quantidade):Number(body.quantidade);p.saldo=(Number(p.saldo)+delta).toFixed(3);const m={...body,id:String(movimentos.length+1),quantidade:String(delta),saldo_apos:p.saldo,registrado_por:usuario,registrado_em:'2026-01-01T12:00:00Z'};movimentos=[m,...movimentos];return reply(200,m);}
 return reply(404,{detail:'não encontrado'});
});
const listen=s=>new Promise(resolve=>s.listen(0,'127.0.0.1',()=>resolve(s.address().port)));async function freePort(){const s=createServer(),p=await listen(s);await new Promise(r=>s.close(r));return p;}
async function waitFor(fn,label){for(let i=0;i<120;i++){try{if(await fn())return;}catch{}await new Promise(r=>setTimeout(r,100));}throw new Error('Timeout: '+label);}
let vite,firefox,ws;
try{
 const apiPort=await listen(server),port=await freePort(),debug=await freePort();vite=spawn(process.execPath,['node_modules/vite/bin/vite.js','--host','127.0.0.1','--port',String(port),'--strictPort'],{cwd:root,env:{...process.env,VITE_API_URL:`http://127.0.0.1:${apiPort}`},stdio:'ignore'});const origin=`http://127.0.0.1:${port}`;await waitFor(async()=>(await fetch(origin)).ok,'vite');
 firefox=spawn('firefox',['--headless','--no-remote','--profile',profile,'--remote-debugging-port',String(debug)],{stdio:'ignore'});await waitFor(async()=>{await fetch(`http://127.0.0.1:${debug}/`);return true;},'firefox');ws=new WebSocket(`ws://127.0.0.1:${debug}/session`);await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});let seq=0;const pending=new Map();ws.addEventListener('message',({data})=>{const b=JSON.parse(data),p=pending.get(b.id);if(p){clearTimeout(p.timer);pending.delete(b.id);b.type==='error'?p.reject(new Error(b.message)):p.resolve(b.result);}});
 function command(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error(method)),15000);pending.set(id,{resolve,reject,timer});ws.send(JSON.stringify({id,method,params}));});}
 await command('session.new',{capabilities:{alwaysMatch:{}}});const {context}=await command('browsingContext.create',{type:'tab'});
 async function evaluate(expression){const r=await command('script.evaluate',{expression,target:{context},awaitPromise:true});if(r.type==='exception')throw new Error(r.exceptionDetails.text);return r.result.value;}
 const click=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);const waitText=t=>waitFor(()=>evaluate(`document.body.textContent.includes(${JSON.stringify(t)})`),t);
 const fill=(selector,value)=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
 await command('browsingContext.navigate',{context,url:origin+'/login',wait:'complete'});await evaluate(`localStorage.setItem('token','ficticio');localStorage.setItem('relaxabarber:filial:${usuario}','${filial}')`);
 await command('browsingContext.setViewport',{context,viewport:{width:1440,height:1000}});await command('browsingContext.navigate',{context,url:origin+'/estoque',wait:'complete'});await waitText('Item 1');assert.equal(await evaluate('document.querySelectorAll("tbody tr").length'),8);await click('.est-paginacao button:last-child');await waitText('Página 2 de 2');
 await fill('.est-busca input','Item 1');await waitFor(()=>evaluate('document.querySelectorAll("tbody tr").length===2'),'busca');await click('.est-limpar');
 await click('.est-acoes-topo .est-dourado');await waitText('Novo item');await fill('.est-modal input[required]','Produto teste');
 await click('.cp-catalogo:nth-child(1) button');await fill('.cp-novo input','Categoria teste');await click('.cp-novo button');await waitFor(()=>evaluate('document.querySelector(".cp-catalogo select").value !== ""'),'categoria');
 await click('.cp-catalogo:nth-child(2) button');await fill('.cp-novo input','Marca teste');await click('.cp-novo button');await waitFor(()=>evaluate('document.querySelectorAll(".cp-catalogo select")[1].value !== ""'),'marca');
 await click('.est-modal button[type=submit], .est-modal form footer .est-dourado');await waitText('Produto teste');
 await click('button[aria-label="Movimentar e ver histórico de Produto teste"]');await waitText('Histórico de movimentações');await fill('.est-modal input[type=number]','3');await fill('.est-modal input[maxlength="1000"]','Entrada de teste');await click('.est-modal form .est-dourado');await waitText('Movimentação registrada.');await waitText('Entrada de teste');
 for (const [tipo,quantia,motivo] of [['baixa','1','Consumo de teste'],['ajuste','-1','Ajuste de teste']]) {
  await evaluate(`(()=>{const e=document.querySelector('.est-modal select');Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(e,${JSON.stringify(tipo)});e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await fill('.est-modal input[type=number]',quantia);await fill('.est-modal input[maxlength="1000"]',motivo);await click('.est-modal form .est-dourado');await waitText(motivo);
 }
 assert.equal(await evaluate('document.querySelectorAll(".est-historico li").length'),3);
 await click('.est-fechar');await click('button[aria-label="Editar Produto teste"]');await waitText('Editar item: Produto teste');
 assert.ok(await evaluate('location.pathname === "/estoque/novo/editar"'));
 assert.equal(await evaluate('document.querySelectorAll(".pe-historico li").length'),3);
 assert.equal(await evaluate('document.querySelectorAll(".cp-cartoes input:checked").length'),1);
 assert.ok(await evaluate('document.querySelector(".cp-catalogo select").value !== "" && document.querySelectorAll(".cp-catalogo select")[1].value !== ""'));
 await click('.cp-cartoes label:nth-child(2)');
 assert.equal(await evaluate('document.querySelectorAll(".cp-cartoes input:checked").length'),2);
 await fill('.pe-grade input[required]','Produto editado');
 await fill('.pe-tres label:nth-child(1) input','20');await fill('.pe-tres label:nth-child(2) input','50');await fill('.pe-tres label:nth-child(3) input','15');
 assert.ok(await evaluate('document.querySelector(".pe-margem strong").textContent.includes("60")'));
 if (process.env.QA_SCREENSHOTS) await writeFile('/src/.visual-produto-desktop.png', Buffer.from((await command('browsingContext.captureScreenshot',{context})).data,'base64'));
 await command('browsingContext.setViewport',{context,viewport:{width:390,height:844}});
 assert.ok(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'));
 if (process.env.QA_SCREENSHOTS) await writeFile('/src/.visual-produto-mobile.png', Buffer.from((await command('browsingContext.captureScreenshot',{context})).data,'base64'));
 await click('.pe-rodape button');await waitText('Produto editado');
 assert.ok(chamadas.some(([m,p,f])=>m==='PUT'&&p==='/estoque/produtos/novo'&&f===filial));
 await click('button[aria-label="Editar Produto editado"]');await waitText('Editar item: Produto editado');await click('.pe-movimentar');await waitText('Histórico de movimentações');
 assert.equal(await evaluate('document.querySelector(".est-modal select").value'),'ajuste');
 await command('browsingContext.navigate',{context,url:origin+'/estoque/inexistente/editar',wait:'complete'});await waitText('Item não encontrado nesta filial.');
 perfil='recepcao';await command('browsingContext.navigate',{context,url:origin+'/estoque/novo/editar',wait:'complete'});await waitText('Sem permissão para editar produtos.');
 assert.ok(chamadas.some(([m,p,f])=>m==='POST'&&p.endsWith('/movimentos')&&f===filial));await command('browsingContext.setViewport',{context,viewport:{width:390,height:844}});assert.ok(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'));
 console.log('Navegador: paginação, busca, cadastro, edição, entrada, baixa, ajuste, histórico e largura mobile aprovados.');
}finally{ws?.close();vite?.kill('SIGTERM');firefox?.kill('SIGTERM');await new Promise(r=>server.close(r));await rm(profile,{recursive:true,force:true});}
