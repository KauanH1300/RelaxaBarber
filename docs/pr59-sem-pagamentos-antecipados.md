# Pagamentos após início e cancelamento pré-atendimento

## Regra

Novos recebimentos exigem agendamento `em_atendimento` ou `concluido`, controle financeiro verificado, financeiro aberto e todas as validações existentes de filial, perfil, comanda e saldo. Comanda aberta e habilitação financeira administrativa não comprovam início do atendimento.

A mesma validação atende `POST /comandas/{id}/recebimentos` e `POST /comandas/{id}/fechamento-financeiro` com pagamentos. A recuperação idempotente de lançamentos históricos ocorre antes da nova validação de estado, sem inserir pagamentos adicionais. Fechamento de quitação histórica sem novos pagamentos mantém seu contrato anterior.

O início continua representado pelo status operacional; esta entrega não adiciona horário efetivo nem altera as regras de data retroativa do recebimento.

## Cancelamento e consulta

O cancelamento interno exige motivo não vazio (até 1000 caracteres), `confirmado: true` estritamente booleano e `atualizado_em_esperado`. A versão é conferida depois do lock do agendamento. Uma operação concorrente que altera a versão impede o cancelamento da tela anterior. O cancelamento preserva itens, vínculos e autoria; não realiza estornos. Os bloqueios financeiros e os estados operacionais permitidos permanecem os anteriores.

A interface usa modal com motivo e confirmação explícita. Conflito ou resultado indeterminado bloqueiam reenvio até nova consulta. A agenda aceita `incluir_cancelados=true`, mantendo o padrão anterior de ocultá-los. A consulta exibe motivo, autor, horário do cancelamento e histórico de reagendamentos. Escopo de filial e profissional continua obrigatório. O portal do cliente foi adaptado ao contrato compartilhado, preservando sua confirmação e motivo existentes.

## Validação local

- 50 testes de integração no PostgreSQL descartável: 41 dos novos cenários e 9 de compatibilidade com cancelamento de comanda, portal e concorrência de status.
- 136 testes de backend sem banco externo: contratos, permissões, transições e atomicidade diretamente afetados.
- 49 testes de frontend: financeiro, recebimentos, permissões e reagendamento.
- Firefox real com API simulada local: `cancelamentoAgendamento.browser.mjs` e `QA59_ONLY=1 node tests/financeiro.browser.mjs`. Confirmação, motivo, versão, clique duplo, conflito, histórico, estados financeiros e layouts de 1440/768/320 px.
- `npm run build` e `npm run lint` aprovados. O build emite aviso de bundle acima de 500 kB.

Os testes de integração usam exclusivamente o destino local validado por `integration_tests/conftest.py`, em contêiner sem acesso à rede externa. Não foram executadas suítes completas nem auditorias anteriores.

Sem migração, alteração de registros históricos ou aplicação no Supabase QA/produção. Sem Pix integrado, estornos pré-atendimento, edição de duração, antecedência mínima ou novo estado operacional. A atualização dos ambientes fica fora desta entrega.
