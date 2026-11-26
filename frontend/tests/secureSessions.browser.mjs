import {createServer} from 'node:http';
import {readFileSync,existsSync,mkdtempSync} from 'node:fs';
import {join,extname} from 'node:path';
import {tmpdir} from 'node:os';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
let active=false; const calls=[];
const server=createServer(async(req,res)=>{
 const path=req.url.split('?')[0];
 if(path.startsWith('/auth/')||path==='/filiais'||path.startsWith('/agendamentos')&&!req.headers.accept?.includes('text/html')){
  calls.push({path,headers:req.headers});
  res.setHeader('Content-Type','application/json');
  if(path==='/auth/csrf'){res.setHeader('Set-Cookie','rb_equipe_csrf=anon; HttpOnly; SameSite=Lax; Path=/');return res.end(JSON.stringify({csrf:'csrf-fixture'}));}
  if(path==='/auth/login'){assert.equal(req.headers['x-equipe-csrf'],'csrf-fixture'); active=true;res.setHeader('Set-Cookie','rb_equipe_sessao=opaque-fixture; HttpOnly; SameSite=Lax; Path=/');return res.end('{}');}
  if(path==='/auth/logout'){assert.equal(req.headers['x-equipe-csrf'],'csrf-fixture');active=false;res.setHeader('Set-Cookie','rb_equipe_sessao=; Max-Age=0; Path=/');res.statusCode=204;return res.end();}
  if(!active){res.statusCode=401;return res.end('{}');}
  return res.end(JSON.stringify(path==='/auth/me'?{id:'fixture',nome:'Equipe teste',perfil:'admin',email:'equipe@example.com'}:[]));
 }
 let file=join(process.cwd(),'dist',path==='/'?'index.html':path);
 if(!existsSync(file))file=join(process.cwd(),'dist/index.html');
 res.setHeader('Content-Type',({'.js':'application/javascript','.css':'text/css','.html':'text/html','.png':'image/png','.jpg':'image/jpeg'})[extname(file)]||'application/octet-stream');
 res.end(readFileSync(file));
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const origin='http://127.0.0.1:'+server.address().port;
const browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless=new','--disable-gpu','--remote-debugging-port=9237','--user-data-dir='+mkdtempSync(join(tmpdir(),'rb-secure-')),'about:blank'],{stdio:'ignore',windowsHide:true});
let ws;try{
 let pages;
 for(let i=0;i<80;i++){try{pages=await(await fetch('http://127.0.0.1:9237/json')).json();break;}catch{await new Promise(r=>setTimeout(r,150));}}
 ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let id=0;const pending=new Map();ws.onmessage=e=>{let m=JSON.parse(e.data);if(m.id){pending.get(m.id)?.(m);pending.delete(m.id);}};
 const send=(method,params={})=>new Promise(r=>{let n=++id;pending.set(n,r);ws.send(JSON.stringify({id:n,method,params}));});
 const evaluate=async(expression)=>(await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})).result?.result?.value;
 const wait=async(expression)=>{for(let i=0;i<100;i++){if(await evaluate(expression))return;await new Promise(r=>setTimeout(r,100));}throw Error('Timeout '+expression);};
 await send('Page.navigate',{url:origin+'/login'});
 await wait("!!document.querySelector('input[type=email]')");
 await evaluate("localStorage.setItem('token','old-unsafe');sessionStorage.setItem('token','old-unsafe');location.reload()");
 await wait("!!document.querySelector('input[type=email]')");
 assert.equal(await evaluate("localStorage.getItem('token')"),null);
 await evaluate(`(()=>{for(const [s,v] of [['input[type=email]','equipe@example.com'],['input[type=password]','senha de teste longa']]){let e=document.querySelector(s);Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,v);e.dispatchEvent(new Event('input',{bubbles:true}));}document.querySelector('form').requestSubmit();})()`);
 await wait("location.pathname==='/agendamentos'");
 assert.equal(await evaluate("document.cookie.includes('rb_equipe_sessao')"),false);
 assert.equal(await evaluate("sessionStorage.getItem('token')"),null);
 await evaluate('location.reload()');await wait("!!document.querySelector('.app-shell')");
 assert.equal(calls.some(c=>c.headers.authorization),false);
 await evaluate("document.querySelector('button[title=Sair]').click()");
 await wait("location.pathname==='/login'");
 await send('Browser.close');
 console.log('PASS Edge: login, HttpOnly, limpeza de tokens antigos, reload/restauração, logout, CSRF e ausência de Authorization; API simulada.');
}finally{ws?.close();browser.kill();server.closeAllConnections();server.close();}
