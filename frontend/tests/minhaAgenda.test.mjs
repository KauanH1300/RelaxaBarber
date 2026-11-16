import test from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { carregarTs } from './helpers/carregarTs.mjs';
const api=await carregarTs('services/minhaAgenda.ts');
const {apiPortal}=await carregarTs('services/portalCliente.ts');
const {CartaoAgendamento,MeusAgendamentos}=await carregarTs('pages/portal/MeusAgendamentos.tsx');
const {destinoAposLogin,sufixoRetorno}=await carregarTs('services/agendamentoPublico.ts');
const reserva={id:'reserva',filial:'Barbearia',servicos:[{nome:'Corte',duracao:30,valor:'35.00'}],barbeiro:{id:'prof',nome:'Profissional'},data:'2099-05-20',hora_inicio:'10:00:00',hora_fim:'10:30:00',duracao:30,valor:'35.00',status:'pendente',atualizado_em:null};

test('cartao mostra dados da reserva sem confundir valor com pagamento',()=>{
  const html=renderToStaticMarkup(createElement(CartaoAgendamento,{a:reserva}));
  for(const item of ['Corte','Profissional','20/05/2099','10:00','10:30','30 min','35,00','Pendente','valor reservado'])assert.ok(html.includes(item));
  assert.ok(!html.includes('comanda_id'));
});
test('pagina protegida inicia sem revelar dados e tem navegacao separada',()=>{
  const html=renderToStaticMarkup(createElement(MemoryRouter,null,createElement(MeusAgendamentos)));
  assert.ok(html.includes('Carregando seus agendamentos'));assert.ok(html.includes('/cliente/conta'));assert.ok(!html.includes('Profissional'));
});
test('APIs usam exclusivamente cookie, sem identidades ou valores forjados',async()=>{
  const calls=[];apiPortal.defaults.adapter=async config=>{calls.push(config);return {status:200,data:[],config};};
  await api.meusAgendamentos();await api.meuAgendamento('reserva');await api.opcoesRemarcacao('reserva','2099-05-21','qualquer');
  await api.cancelarMeuAgendamento({...reserva,cliente_id:'forjado',status:'concluido'});
  await api.remarcarMeuAgendamento({...reserva,cliente_id:'forjado'},'2099-05-21','14:15','qualquer');
  assert.deepEqual(JSON.parse(calls[3].data),{atualizado_em_esperado:null});
  assert.deepEqual(JSON.parse(calls[4].data),{atualizado_em_esperado:null,data:'2099-05-21',hora_inicio:'14:15',barbeiro_id:null});
  assert.ok(calls.every(c=>c.withCredentials===true&&!c.headers.Authorization));
  assert.equal(calls[2].params.barbeiro_id,undefined);
});
test('retorno de login aceita apenas destinos internos conhecidos',()=>{
  assert.equal(destinoAposLogin('?retorno=meus-agendamentos'),'/cliente/agendamentos');
  assert.equal(sufixoRetorno('?retorno=meus-agendamentos'),'?retorno=meus-agendamentos');
  assert.equal(destinoAposLogin('?retorno=https://hostil.example'),'/cliente');
  assert.equal(destinoAposLogin('?retorno=agendamento'),'/agendar?etapa=confirmacao');
});
