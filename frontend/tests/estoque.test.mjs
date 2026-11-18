import assert from 'node:assert/strict';
import test from 'node:test';
import { carregarTs } from './helpers/carregarTs.mjs';
const { situacao, indicadores, filtrar, csv } = await carregarTs('pages/estoque/estoqueUtils.ts');
const item = { id:'1', nome:'Pomada', unidade:'un', venda:true, consumo:true, custo:'2.50', preco_venda:'5.00', estoque_minimo:'2.000', saldo:'2.000', ativo:true };
test('classifica saldo e calcula indicadores somente com itens ativos', () => {
  const esgotado = {...item,id:'2',saldo:'0'}; const inativo = {...item,id:'3',ativo:false,saldo:'10'};
  assert.equal(situacao(item),'baixo'); assert.equal(situacao(esgotado),'esgotado'); assert.equal(situacao(inativo),'inativo');
  assert.deepEqual(indicadores([item,esgotado,inativo]),{total:3,ativos:2,venda:3,consumo:3,baixo:1,esgotado:1,valor:5});
});
test('filtros combinam nome, finalidade e situação sem excluir dupla finalidade', () => {
  assert.equal(filtrar([item], 'pom', 'consumo', 'baixo').length,1);
  assert.equal(filtrar([item], 'pom', 'venda', 'baixo').length,1);
  assert.equal(filtrar([item], 'pom', 'venda', 'esgotado').length,0);
});
test('CSV escapa fórmulas e aspas e inclui todos os itens fornecidos', () => {
  const result = csv([{...item,nome:'=2+2'}, {...item,id:'2',nome:'Nome "especial"'}]);
  assert.match(result, /"'=2\+2"/); assert.match(result, /"Nome ""especial"""/); assert.equal(result.split('\r\n').length,3);
});
