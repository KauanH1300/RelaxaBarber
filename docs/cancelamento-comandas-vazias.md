# Cancelamento direto de comandas vazias

`POST /comandas/{id}/cancelamento?filial_id={filial}` exige `Idempotency-Key` UUID e corpo:

```json
{"versao": 0, "motivo": "Comanda aberta sem serviços", "confirmado": true}
```

Somente ADMIN e RECEPCAO com acesso ativo à filial podem executar. O servidor relê usuário, vínculos, agendamento e comanda sob os mesmos locks das operações financeiras: usuário/filial, agendamento e comanda. A transação relê a versão e verifica a existência de registros, sem inferir ausência de movimentação pelo saldo.

São elegíveis comandas pendentes ou abertas sem data de fechamento, sem itens ativos e sem pagamentos, estornos, fechamentos, benefícios ou habilitação financeira posterior. Itens removidos têm `ativo=false`: continuam preservados, mas não impedem o cancelamento. Auditorias de inclusão/remoção de serviços são preservadas e não equivalem a movimentação financeira.

O controle financeiro inicial é um registro de suporte, criado junto com a comanda, e não impede cancelar. Ausência de controle significa histórico não verificado e bloqueia o fluxo; controle com chave de habilitação também bloqueia. Essa política evita tratar legado desconhecido ou pagamento integralmente estornado como ausência de movimentação.

O cancelamento altera somente `comandas.status` para `cancelada` e incrementa `versao_itens`. Não apaga itens, controle, histórico ou agendamento, não altera preços e não cria pagamento, estorno ou fechamento. A nova tabela `cancelamentos_comanda` preserva autor, timestamp do banco, motivo, chave, fingerprint e resposta original. A auditoria é imutável, com grants restritos ao runtime e proteção contra UPDATE/DELETE/TRUNCATE. O detalhe da comanda expõe a auditoria em `cancelamento`.

Mesma chave e mesmo corpo recuperam a resposta original; corpo diferente produz conflito. Outra chave após cancelamento é rejeitada. Adicionar serviços e as operações financeiras existentes já verificam o estado da comanda e recusam novas operações em `cancelada`. Os replays de operações anteriores continuam sem criar novas movimentações.

O agendamento permanece no estado original. Seu fluxo existente pode cancelá-lo depois quando a transição já for permitida, preservando a auditoria direta. Outras transições incompatíveis continuam bloqueadas: o fluxo não reabre a comanda cancelada nem flexibiliza cancelamento de atendimento iniciado.

Na interface, o botão aparece para gestores em comandas vazias pendentes/abertas. O servidor revalida os impedimentos históricos. São obrigatórios motivo e confirmação explícita; desistir não envia requisição. Durante a operação, os demais fluxos ficam bloqueados. A intenção é preservada no navegador antes do envio, permitindo recuperar a mesma chave e versão após timeout e recarga.

## Migração e validação

- Migração: `d17a60c28e94`, sucessora de `ab72d90e613f`; cria somente a tabela de auditoria, ACLs, política de runtime e triggers.
- Upgrade validado pela cadeia Alembic real em PostgreSQL local descartável; não aplicado no Supabase QA ou produção.
- Downgrade bloqueado para não apagar auditorias; reversão requer plano próprio.
- Testes novos em `backend/integration_tests/test_cancelamento_comanda.py`: permissões e revogação, filial, motivo, confirmação, estados, integridade do agendamento/itens, movimentos com saldo zero, legado e habilitação, concorrência com inclusão e replays, compatibilidade com cancelamento da reserva e imutabilidade.
- Testes de frontend em `frontend/tests/cancelamentoComanda.test.mjs` e `frontend/tests/cancelamentoComanda.browser.mjs`: elegibilidade visual, intenção persistida, timeout/replay, motivo, confirmação, desistência, auditoria e perfis. Firefox usa apenas uma API simulada local; o backend é testado contra PostgreSQL real.
- Build TypeScript/Vite e ESLint validados. Nenhuma auditoria ou suíte anterior foi repetida.

Aplicar a migração em cada ambiente antes de implantar o backend desta versão. Homologação remota e aplicação de migração dependem de autorização específica.
