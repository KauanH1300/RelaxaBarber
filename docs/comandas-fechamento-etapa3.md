# Etapa 3 — integração funcional do frontend

Branch mantida: `feat/comandas-fechamento-integral-atomico`.
Antes das edições foram lidos `comandas-fechamento-etapa2.md`, os schemas HTTP
reais, rotas financeiras e a implementação frontend existente.
Os 58 arquivos previamente modificados/não rastreados foram copiados byte a byte,
com manifesto SHA256, para
`C:\Users\kauan\AppData\Local\Temp\relaxabarber-etapa3-20261114-183439`.
Nenhuma nova branch, commit, stash, push, migração ou mudança de backend.

## Fluxo implementado

1. Consultar o financeiro autorizado da comanda. Atendimento concluído e situação
   financeira continuam distintos. Uma conclusão operacional não dispara pagamento.
2. Para financeiro verificado e aberto, informar de 1 a 16 recebimentos positivos,
   por Pix, crédito, débito ou dinheiro. Composição e soma usam centavos inteiros.
   A soma deve ser exatamente o restante líquido retornado pelo backend.
3. Confirmar explicitamente cada recebimento. Alterar valor, método ou data exige
   nova confirmação dos dados alterados. Não existe opção de saldo futuro.
4. Revisar lista, valores, métodos, datas e motivo. A confirmação envia um único
   `POST /comandas/{id}/fechamento-financeiro`, com a lista de pagamentos e
   `confirmado: true` em cada um, mais `Idempotency-Key` e filial existentes.
5. Após sucesso, consultar novamente resumo/histórico, detalhes e painel agregado.
   Atualização não fecha o diálogo e também alcança os indicadores se o usuário
   fechar o diálogo enquanto o POST ainda está em andamento.

O resumo principal contém somente **Valor Total** e **Valor Recebido**, sendo o
segundo líquido de estornos. O restante aparece na preparação do recebimento.
Histórico, estornos e identificadores mantêm sua fonte persistida, em áreas
secundárias. Não foi copiado o layout Stitch nem adicionada funcionalidade fictícia.

O indicador agregado de pagamentos continua indisponível porque o painel backend
não fornece esse cálculo. Não é inferido usando somente os cards visíveis.
Os indicadores existentes são atualizados por nova consulta ao servidor.

## Históricos e permissões

- Comanda verificada já quitada permite finalizar com lista vazia, sem nova cobrança.
- Total zero exige motivo e não cria recebimento de valor zero.
- Registros sem verificação continuam com recebido desconhecido; nenhuma dívida,
  quitação, ativação ou conciliação é inferida automaticamente.
- Comandas antigas fechadas operacionalmente dependem do financeiro verificado.
  A interface informa que o status histórico isolado não comprova pagamento.
- ADMIN e RECEPÇÃO mantêm o escopo autorizado; ambos os perfis de barbeiro só
  consultam financeiro próprio. O backend continua sendo a autoridade final.
- Estorno novo é apresentado apenas ao ADMIN, para históricos financeiramente
  abertos e dentro do líquido disponível do pagamento selecionado, com motivo.
- Após fechamento, novos estornos continuam bloqueados. Não foi criada reabertura.
- Falhas 401/403/404 removem os dados de detalhe quando o acesso deixa de existir;
  o interceptor de contexto/filial existente permanece em uso.

## Idempotência e recuperação

O envio tem trava síncrona além de loading e campos desabilitados. Antes do POST,
a intenção completa é validada e gravada em `sessionStorage`, mantendo a chave
existente por usuário, filial e comanda. Outra pendência não é sobrescrita.

Timeout, erro de transporte, 5xx, confirmação indeterminada e conflito de chave
preservam a intenção. A recuperação relê a operação original, sem recalcular
valores, reordenar a lista, atualizar datas ou gerar nova chave. Consultar o
financeiro não elimina uma pendência, mesmo se ele já aparecer fechado.

Erro definitivo na primeira tentativa permite corrigir o formulário, após nova
consulta automática. Erro durante recuperação de uma intenção anterior mantém
o registro: uma rejeição atual não prova ausência de confirmação anterior.

Falha de storage antes do envio bloqueia o POST. Falha ao remover a pendência
após sucesso mantém a chave para replay; o recebimento confirmado não é enviado
como outra operação. Falha do GET posterior é apresentada como falha de consulta,
sem invalidar o sucesso do POST nem sugerir nova cobrança.

Se o diálogo que enviou for desmontado durante o POST, ele atualiza os indicadores
após sucesso, mas mantém a intenção no storage. Isso evita apagar a pendência que
um diálogo reaberto já carregou. A nova montagem pode recuperar a operação e
remover o registro após confirmação, sempre com a chave original.

Pendências antigas de fechamento sem lista continuam válidas. Pendências antigas
`pagamentos` só podem usar uma função dedicada de recuperação do storage original.
O caminho de novos envios rejeita `pagamentos`, inclusive em runtime. A interface
não cria novos pagamentos avulsos. O backend só permite replay nesse endpoint.
Se o pagamento antigo não existia, o 409 mantém a pendência para revisão pelo
administrador; não há conversão automática para uma nova cobrança.

Conteúdo corrompido ou inesperado, incluindo parcelas sem confirmação, bloqueia
a operação e permanece armazenado. Não é apagado ou reinterpretado como quitação.

## Arquivos alterados nesta etapa

- `frontend/src/services/financeiro.ts`: tipos discriminados, composição integral,
  validação de payload/storage e separação entre novo envio e recuperação antiga.
- `frontend/src/pages/comandas/FinanceiroComanda.tsx`: formulário integral,
  confirmação por recebimento, resumo reduzido, áreas secundárias e recuperação.
- `frontend/src/pages/comandas/DetalheComanda.tsx`: atualização após sucesso,
  preservação do diálogo, remoção de dados após revogação e textos de estados.
- `frontend/src/pages/comandas/Comandas.tsx`: atualização automática do painel e orientação.
- `frontend/src/pages/comandas/ComponentesComanda.tsx`: textos dos indicadores compatíveis
  com atendimento concluído e ausência de agregado financeiro no contrato.
- `frontend/src/pages/comandas/Comandas.css`: ajustes mínimos de parcelas, checkbox e áreas secundárias.
- `frontend/tests/financeiro.test.mjs`: contrato integral, centavos, estados, storage e replay.
- `frontend/tests/financeiro.browser.mjs`: Firefox com API local, cobrindo o novo fluxo e falhas.
- `frontend/tests/comandas.test.mjs`: orientação de estados no detalhe.
- Este relatório, criado agora.

Package.json, logo, lockfiles, backend, migrations, scripts de QA remoto e evidências
anteriores foram preservados. Nenhuma dependência da aplicação foi adicionada.

## Validação e limites

Testes executados em containers descartáveis com `--network none`, checkout
somente leitura e cópia efêmera do frontend dentro do container. Firefox ESR
usa Vite e API simulada exclusivamente no loopback, com URL explícita.
Não foram executados os scripts `*.supabase.mjs` ou os executores de QA remoto.
Não foi necessário banco: esta etapa não executa integração PostgreSQL, migrations
ou acesso ao Supabase. Os testes de transação real permanecem os da Etapa 2.

Comandos usados dentro da imagem local derivada para testes:

```text
node /source/tests/helpers/validarFrontend.cjs
node /source/tests/helpers/validarFrontend.cjs --browser
node /source/tests/helpers/validarFrontend.cjs --browser --financeiro-only
```

Os primeiros testes identificaram expectativas antigas de pagamento avulso e
um helper removido ainda declarado. Foram atualizados/removido, e todos os checks
foram repetidos. A injeção de falha de storage passou a alterar o prototype real
do Firefox e comprovar a falha antes de clicar. O leitor BiDi foi corrigido para
representar `null`, em vez de confundi-lo com `undefined`. Essas correções são
do executor de testes; não alteram regras financeiras.

Resultados finais:

- **126 testes frontend aprovados**, incluindo cinco novos testes financeiros.
- TypeScript (`tsc -b`), Vite build e ESLint: **aprovados**, exit 0.
- Firefox: suíte de comandas **aprovada** (cards, indicadores, paginação, detalhe,
  Escape/foco, filtros, loading, erros, filial, perfis e mobile).
- Firefox: suíte financeira integral **aprovada** após os ajustes finais. Cobriu
  rejeição de soma insuficiente/excessiva e falta de confirmação; múltiplos
  métodos em um POST; estornos históricos; atualização automática de detalhe e
  indicadores; clique duplo; limite de 16 sob cliques rápidos; storage indisponível,
  corrompido e falha de limpeza após sucesso; erro 422; falha de GET posterior;
  timeout/replay após navegar; fechar e reabrir o diálogo durante o POST;
  recuperação de pendência antiga; quitação anterior; total zero; atendimento
  não concluído; legado; 403/404; quatro perfis; largura mobile e foco.
- `git diff --check`: **aprovado**.

O manifesto confirmou 51 dos 58 arquivos anteriores byte a byte inalterados,
incluindo todo o backend e as evidências anteriores. Os sete arquivos diferentes
receberam os ajustes frontend listados acima; outros dois arquivos frontend
anteriormente limpos também foram alterados. O relatório é o único arquivo novo.
Não foram executados commit, push ou comandos Git destrutivos.

Limitações preservadas: confirmação de recebimento é declarada pelo operador;
não há gateway bancário automático. A recuperação em sessionStorage depende da
mesma aba/sessão do navegador e não é garantida após limpar storage ou fechar a
aba. Pendência antiga rejeitada/corrompida exige revisão, sem botão para apagar
automaticamente uma intenção financeira incerta. Validação com API simulada não
substitui um teste ponta a ponta com backend real ou homologação operacional.
