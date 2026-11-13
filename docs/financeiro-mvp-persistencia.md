# Persistência financeira do MVP

Esta etapa complementa e preserva `financeiro-mvp-arquitetura.md`. As regras
aprovadas no pedido atual substituem as alternativas daquele documento: não há
reabertura; fechamento é explícito; excedentes são proibidos; total zero exige
motivo; estorno é exclusivo de ADMIN; retroatividade até sete dias para usuários
autorizados e, acima disso, somente ADMIN. Nenhum serviço financeiro ou endpoint
foi disponibilizado nesta etapa.

## Modelo implementado

| Tabela | Função e invariantes locais |
| --- | --- |
| controles_financeiros_comanda | Uma ativação explícita por comanda, filial, responsável, motivo obrigatório e registro do servidor. Ausência significa histórico não verificado. |
| pagamentos_comanda | Recebimento positivo, forma dinheiro/pix/debito/credito, data efetiva, registro do servidor, responsável, UUID de idempotência e fingerprint de 64 caracteres. |
| estornos_pagamento | Lançamento positivo compensatório, pagamento/comanda/filial originais, motivo obrigatório, data efetiva, registro, responsável e idempotência. Não apaga o original. |
| fechamentos_financeiros_comanda | Um fechamento definitivo por comanda, responsável, registro do servidor, total e recebido líquido congelados, idempotência e motivo obrigatório para total zero. |

`Comanda.situacao_financeira` é uma propriedade derivada: `nao_verificado` sem
controle, `aberto` com controle sem fechamento, `fechado` com fechamento. Não
depende do status operacional. O banco representa os mesmos estados pela
ausência/presença das linhas; não existe enum de status editável ou projeção
redundante que possa divergir do histórico. Parcial/quitado serão derivados dos
agregados pelo serviço; não são inferidos apenas de `status='fechada'`.

Controle e fechamento são fatos auditados, em vez de uma tabela genérica de
eventos que permitiria reabertura. Nenhuma tabela atual é backfilled, nem se
altera o fechamento operacional. A única alteração estrutural em `comandas` é
UNIQUE (id, filial_id), necessária para FKs compostas. O backend atual continua
criando comandas sem controle, inclusive após aplicar a migração: ativação de
novas comandas precisa ser coordenada com o serviço futuro, antes de habilitar
qualquer fluxo financeiro. A conciliação do legado permanece manual e pendente.

Recebimentos e fechamentos referenciam (comanda_id, filial_id) do controle, que
referencia o mesmo contexto da comanda. Estornos referenciam o contexto completo
do pagamento original. FKs RESTRICT preservam os responsáveis e os pais. Não
há cascade de exclusão nem coleções ORM com delete-orphan no financeiro.

Idempotência de pagamento e estorno: UNIQUE (comanda_id, chave_idempotencia),
separadamente por tipo de operação. A mesma chave em outra comanda é permitida.
Fechamento tem PK comanda_id: só pode existir um, mesmo com chaves diferentes;
serviço comparará sua chave e fingerprint antes de responder a uma repetição.
Ativação tem PK comanda_id e deve comparar os dados em uma repetição.

Valores são NUMERIC(10,2), retornados como Decimal. Checks exigem valores
positivos para pagamentos/estornos; totais entre zero e 99.999.999,99; os limites
também recusam NaN. O snapshot do fechamento exige total = recebido_liquido.
O tipo ORM `ValorFinanceiro` rejeita floats, valores não finitos, excesso de
faixa e frações de centavo, evitando arredondamento silencioso pelo ORM.
SQL direto em NUMERIC(10,2) ainda pode arredondar: não expor INSERT SQL livre ao
cliente; a futura entrada de serviços também deve validar Decimal e escala.
Checks do snapshot não demonstram, sozinhos, que ele coincide com o livro/itens.

## Imutabilidade e segurança PostgreSQL

A revisão `d93a7e2f610c`, sucessora direta de `c82f6a1d904b`, cria todas as
estruturas, constraints, triggers, RLS e ACLs na mesma transação PostgreSQL, sem
autocommit/commits intermediários. Os três arquivos da etapa anterior foram
preservados.

Triggers de INSERT impõem `registrado_em=clock_timestamp()` mesmo se o chamador
enviar outra data. Data efetiva é separada e deve ser finita. Triggers de
UPDATE/DELETE/TRUNCATE bloqueiam mutações nas quatro tabelas, inclusive para o
proprietário em operação normal. As funções são SECURITY INVOKER, com search_path
pg_catalog e EXECUTE público revogado. Usuário privilegiado ainda pode desativar
triggers ou alterar o schema: isso não é proteção contra um administrador do DB.

RLS habilitada, policies SELECT/INSERT somente para relaxabarber_runtime;
grants materializados de PUBLIC/anon/authenticated/service_role/runtime são
revogados, inclusive por coluna, e apenas SELECT/INSERT são concedidos ao
runtime. A migração falha se os papéis externos ainda herdarem acesso ou se o
runtime herdar poderes incompatíveis. Não cria roles, memberships ou alterações
globais de default privileges. O migrador precisa do mesmo pré-requisito de
runtime não administrativo já exigido pela revisão anterior.

As policies do runtime são intencionalmente de acesso do backend, não de
identidade do usuário final. Não implementam autorização por filial/profissional
nem a exclusividade de ADMIN para estorno: o login PostgreSQL é compartilhado.
O backend atual usa postgres e ignora RLS; não confundir essa camada com proteção
contra escrita privilegiada. Acesso a faturamento será independente da agenda.

Downgrade adquire ACCESS EXCLUSIVE nas tabelas financeiras antes de verificar
dados. Se houver qualquer controle ou lançamento, falha sem remover estruturas
ou histórico. Somente quando as quatro tabelas estão vazias remove tabelas,
funções e a UNIQUE nova, sem tocar em comandas, clientes ou expediente.

## Obrigações da próxima camada de serviços

- Revalidar usuário ativo e filial autorizada. ADMIN/RECEPCAO podem operar no
  contexto autorizado; BARBEIRO e BARBEIRO_CHEFE apenas próprias comandas.
  Relatório global somente ADMIN; recepção por filial; barbeiros/chefes apenas
  próprios recebimentos. Não reutilizar leitura ampla da agenda do chefe.
- Exigir atendimento concluído, controle financeiro verificado e comanda não
  fechada para novos recebimentos. Nunca ativar ou cobrar legado automaticamente.
- Fonte autoritativa do total: soma Decimal de quantidade × preço congelado dos
  itens, não catálogo atual ou valor_total possivelmente divergente. Validar
  itens/range e impedir alterações após começar a receber.
- Sob locks na ordem usuário/contexto, agendamento FOR UPDATE, comanda FOR UPDATE,
  calcular pagamentos menos estornos e saldo. Recusar recebimento acima do saldo;
  permitir parciais/múltiplas formas. Estorno cumulativo não pode exceder original.
  CHECK de linha não garante esses agregados nem concorrência entre chaves distintas.
- Fechar explicitamente somente se o saldo real for zero. Para total zero,
  exigir motivo. Ler total/livro e gravar snapshot no mesmo commit. Não implementar
  reabertura. O banco impede segundo fechamento e mutação do primeiro.
- Estorno só ADMIN. Correção é estorno + novo lançamento rastreável, nunca UPDATE.
  Ainda decidir o fluxo de estorno após fechamento: mantê-lo como fato histórico
  não reabre a comanda, mas pode reduzir o líquido após a quitação original.
  Não permitir esse fluxo até a regra de negócio ficar explícita.
- Validar data com fuso; guardar efetiva e registro separadamente. Implementar a
  janela aprovada de sete dias e exceção ADMIN. Definir se são 168 horas ou dias
  civis no fuso da filial, limites de datas futuras e data anterior à conclusão;
  esta etapa não escolhe arbitrariamente esses detalhes.
- Canonicalizar payload, gerar/verificar fingerprint, autorizar antes de revelar
  resultado idempotente, retornar original em repetição idêntica e conflito em
  payload diferente. Recuperar confirmação indeterminada com a mesma chave.
  Não continuar após IntegrityError sem rollback/SAVEPOINT apropriado.
- Total, verificação e INSERT devem compartilhar uma transação e lock pai;
  nenhum caminho alternativo de escrita pode ignorar esse protocolo. Serviços
  precisam de testes concorrentes adicionais para saldo, estorno e fechamento.

## Ambiente e evidências de testes

`integration_tests/test_financeiro_persistencia.py` usa exclusivamente o alvo
descartável validado pelo conftest existente. Execução em Docker: PostgreSQL 17,
network none, porta interna 55432 sem publicação, dados em tmpfs e credenciais
fictícias. O executor usa network container:<instância de teste>, compartilhando
somente o loopback sem saída externa; projeto somente leitura, .env não carregado.
Não executar essa suíte no Supabase ou no banco da aplicação.
O container PostgreSQL criado nesta etapa foi encerrado e removido ao final;
nenhum container preexistente foi alterado.

A suíte aplica a cadeia real de migrações em transação como migrador sem poderes
administrativos, testa defaults de privilégios amplos, DDL real upgrade/downgrade,
rollback transacional, legado inalterado, downgrade recusado com histórico,
constraints, datas, FK composta, idempotência concorrente, ACL/RLS e login restrito.
O teste de revisão usa stamp do MigrationContext após DDL real; não executa o
env.py/CLI, que carrega a configuração da aplicação.

Os testes antigos foram ajustados somente quanto ao inventário de tabelas e ao
novo head Alembic. O teste de DDL do expediente passou a apontar para sua revisão
fixa, em vez de presumir que ela será sempre o head. A implementação e as
migrações de expediente e clientes não foram modificadas.

Resultados desta etapa em PostgreSQL 17.11:

- 51 cenários de persistência financeira aprovados; na reexecução, o teste do
  novo head também passou (52 no comando final).
- 45 cenários PostgreSQL de regressão: 44 passaram inicialmente; a única falha
  era a asserção do head anterior, corrigida e reexecutada com sucesso.
- 730 cenários backend sem rede: 729 passaram na suíte completa; a única falha
  era o inventário fixo de tabelas, atualizado e reexecutado com sucesso.
- Upgrade com migrador não administrativo; stamp de revisão no mesmo commit
  da DDL; rollback restaura conjuntamente estruturas e versão. Downgrade vazio
  preserva legado; downgrade com histórico é recusado.

Os testes financeiros não demonstram as regras ainda não implementadas nos
serviços (incluindo saldo, autorização final, retroatividade e estorno ADMIN).

Antes de implantação futura: obter autorização própria, revisar backup/recuperação
(Supabase informado sem backup automático), verificar locks/permissões e ensaiar
com dados representativos. Esta etapa não acessa nem modifica o banco remoto.
