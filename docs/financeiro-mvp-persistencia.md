# Persistência financeira

Referência do modelo implementado, com migrações aditivas e sem backfill de
registros históricos. Regras de autorização e transação em
[serviços financeiros](financeiro-mvp-servicos.md), transporte em
[contratos HTTP](financeiro-mvp-http.md). Não autoriza executar migrações.

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
redundante que possa divergir do histórico. Recebido líquido e quitação são
derivados dos agregados pelo serviço; não são inferidos apenas de `status='fechada'`.

Controle e fechamento são fatos auditados, em vez de uma tabela genérica de
eventos que permitiria reabertura. Nenhuma tabela atual é backfilled, nem se
altera o fechamento operacional. A única alteração estrutural em `comandas` é
UNIQUE (id, filial_id), necessária para FKs compostas. Novas comandas recebem
controle na mesma transação de criação do agendamento.
A migração isolada não ativa legado; conciliação histórica exige fluxo próprio.

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
cliente; a entrada dos serviços valida Decimal e escala antes de persistir.
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
O runtime deve usar identidade restrita; não confundir RLS com proteção contra
conexões privilegiadas. O escopo financeiro é independente da leitura da agenda.

Downgrade adquire ACCESS EXCLUSIVE nas tabelas financeiras antes de verificar
dados. Se houver qualquer controle ou lançamento, falha sem remover estruturas
ou histórico. Somente quando as quatro tabelas estão vazias remove tabelas,
funções e a UNIQUE nova, sem tocar em comandas, clientes ou expediente.

## Auditoria e idempotência de inclusão de serviços

A revisão aditiva `e14a29bc7031`, posterior a `d93a7e2f610c`, cria
`inclusoes_servicos_comanda`, sem atualizar dados históricos. Cada linha associa
item, comanda/filial, responsável, carimbo do servidor, chave, fingerprint e total
resultante da operação. FKs RESTRICT preservam item, contexto e responsável.

- UNIQUE `(comanda_id, chave_idempotencia)` deduplica a inclusão.
- UNIQUE `item_id` vincula cada item a uma única inclusão auditada.
- Checks exigem fingerprint de 64 caracteres e total entre zero e 99999999.99.
- Triggers reutilizam carimbo financeiro e bloqueio de UPDATE/DELETE/TRUNCATE.
- ACL/RLS reutilizam a proteção da revisão financeira anterior; autorização por
  usuário, filial e propriedade continua no backend.

Inclusão, auditoria e idempotência compartilham o commit e os locks do contexto
financeiro. O catálogo é fonte de descrição/preço para o novo item; itens
anteriores não são recalculados. O total canônico é a soma de itens, não um
valor fornecido pelo frontend.

O downgrade da revisão de inclusão adquire ACCESS EXCLUSIVE e recusa remoção
se existir auditoria; somente remove a tabela nova quando vazia. Não aplicar
downgrade ou upgrade em ambiente externo sem autorização específica.

## Validação e implantação

Constraints, ACL/RLS, auditoria, replay e concorrência são exercitados pelas
suítes em `backend/tests/contracts` e `backend/integration_tests`, em especial
`test_financeiro_persistencia.py`, `test_itens_comanda.py` e
`test_fechamento_integral.py`. Integração precisa validar inequivocamente a
identidade do PostgreSQL descartável antes de qualquer DDL ou escrita, sem
carregar configuração de produção. Logs e resultados ficam em `.local-qa/`.

Antes de disponibilizar endpoints em outro ambiente, verificar a cadeia Alembic,
papéis restritos, locks e plano de backup/recuperação. A presença dos arquivos de
migração no repositório não comprova aplicação em nenhum banco.
