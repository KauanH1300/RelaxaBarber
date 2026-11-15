# Financeiro: contratos HTTP

Referência dos endpoints implementados em `backend/app/api/routes/financeiro.py` e
`itens_comanda.py`. Schemas e OpenAPI da aplicação são a fonte do transporte.
Ver [interface de comandas](comandas-interface.md), [persistência](financeiro-mvp-persistencia.md)
e [transações](financeiro-mvp-servicos.md). Não autoriza implantação ou migração.

## Ativação e compatibilidade

`POST /agendamentos` continua usando `criar_agendamento` e sua única fronteira
`transacao_escrita`. A nova comanda recebe, por relacionamento ORM, um
`ControleFinanceiroComanda` com a mesma filial, o usuário autenticado como
`registrado_por` e motivo fixo de ativação. O ORM ordena os INSERTs pelas FKs;
o commit existente confirma agendamento, serviços, vínculo do cliente, comanda,
itens e controle juntos. Falhas antes da confirmação revertem o conjunto.
Não há chamada ao serviço financeiro (que exige sessão limpa), commit adicional,
nova transação de escrita, alteração de default ou atualização em massa.
O refresh pós-commit já existente permanece uma leitura separada: uma falha
nessa leitura não desfaz a criação confirmada. O POST de agendamento continua
sem idempotência própria; não repetir sua criação cegamente após resposta incerta.
As garantias de repetição descritas abaixo são dos novos contratos financeiros.

A revisão `d93a7e2f610c` já permite isso: controle tem PK por comanda, FK composta
por comanda/filial, responsável obrigatório, motivo não vazio e carimbo pelo banco.
Essa revisão precisa existir no banco antes de disponibilizar o financeiro.
A inclusão de serviços também requer a revisão aditiva `e14a29bc7031`.
Aplicação em qualquer ambiente exige autorização e verificação próprias;
esta documentação não comprova a versão instalada em bancos externos.

Ausência de controle continua significando `nao_verificado`. Nenhuma comanda
antiga é ativada, declarada paga ou classificada como devedora. Conciliação será
um fluxo específico auditado; nem ADMIN pode contornar esse bloqueio.

Novas comandas permanecem operacionalmente abertas quando o atendimento é
concluído. Conclusão não cria pagamento nem fechamento financeiro. O fechamento
integral grava pagamentos, fechamento e estado/data da comanda em uma transação.
Estados operacionais históricos são preservados; `status=fechada` isolado não
comprova quitação. As consultas expõem classificação financeira separada, sem
conciliar legado ou transformar cancelamentos em dívida exigível.

## Convenções de transporte e autorização

- Autenticação Bearer existente, usuário ativo, empresa/filial ativas e vínculo
  ativo para não ADMIN. A política existente permite ADMIN nas filiais ativas,
  sem exigir vínculo individual. `id` no path é UUID da comanda; `filial_id` é query UUID opcional usada
  como restrição adicional, nunca para transferir o recurso para outra filial.
  A filial é derivada da comanda, inclusive para ADMIN.
- ADMIN e RECEPCAO consultam, recebem e fecham conforme seu escopo de filial.
  BARBEIRO e BARBEIRO_CHEFE só operam e consultam suas próprias comandas,
  mesmo que o chefe tenha acesso operacional mais amplo à agenda.
  Estorno exige ADMIN, preservando o escopo de filial.
- Recurso ausente, de outro profissional/filial ou pagamento fora da comanda:
  404 uniforme, sem valores, existência ou identificadores de terceiros.
  Usuário autenticado sem permissão financeira ativa: 403.
- JSON com campos desconhecidos rejeitados (422). UUIDs válidos; timestamps
  RFC3339 com offset obrigatório, normalizados para UTC na resposta.
  Datas sem offset ou futuras são inválidas. O transporte aceita precisão até
  microssegundos (mais casas são rejeitadas, evitando truncamento silencioso).
  Números Unix não são aceitos como timestamps.
- Dinheiro no JSON é **string decimal**, nunca float: `"30.50"`. Converter
  diretamente para Decimal; valor finito, positivo, até `99999999.99`, sem fração
  de centavo. A string não aceita sinais, expoentes ou vírgula decimal.
  Saída com duas casas; totais/saldo podem ser zero. Não aceitar
  totais, saldo, filial, autor, fingerprint ou data de registro fornecidos no body.
- POSTs exigem header `Idempotency-Key: <UUID>`, mapeado para
  `chave_idempotencia` do serviço. Não repetir a chave no body.
- Cada escrita usa sessão da requisição e o commit único do serviço existente.
  Respostas são DTOs materializados antes do commit; leitura não faz commit.

## Schemas e operações

### GET /comandas/{id}/financeiro

Sem body. Resposta 200, schema `ResumoFinanceiroOut`. Na etapa 11 o campo
`historico` foi acrescentado de forma aditiva; os campos anteriores mantêm
os mesmos nomes, tipos e significados:

```json
{"comanda_id":"11111111-1111-4111-8111-111111111111","filial_id":"22222222-2222-4222-8222-222222222222","situacao":"aberto","total":"30.50","pagamentos":"10.00","estornos":"2.00","recebido_liquido":"8.00","saldo":"22.50","historico":{"pagamentos":[{"id":"33333333-3333-4333-8333-333333333333","valor":"10.00","forma":"pix","recebido_em":"2026-11-13T13:00:00Z","registrado_em":"2026-11-13T13:01:00Z"}],"estornos":[{"id":"66666666-6666-4666-8666-666666666666","pagamento_id":"33333333-3333-4333-8333-333333333333","valor":"2.00","motivo":"Correção de recebimento","efetivado_em":"2026-11-13T13:02:00Z","registrado_em":"2026-11-13T13:03:00Z"}]}}
```

`situacao`: `nao_verificado | aberto | fechado`. `pagamentos` e `estornos` são
somatórios, não listas. Para legado, esses dois campos, `recebido_liquido` e
`saldo` são **null**; `total` permanece o total dos itens, sem afirmar dívida.
GET não ativa, concilia ou movimenta registros. Não oferece listagem global.

`historico.pagamentos` e `historico.estornos` são listas completas da comanda
autorizada, obtidas dos registros persistidos, inclusive após fechamento.
Cada lista é ordenada por `(registrado_em ASC, id ASC)`: timestamps iguais
são desempatados pelo UUID. Não há ordenação por data efetiva, pois lançamentos
retroativos continuam na ordem em que foram registrados.

Pagamento contém `id`, `valor`, `forma`, `recebido_em`, `registrado_em`.
Estorno contém `id`, `pagamento_id`, `valor`, `motivo`, `efetivado_em`,
`registrado_em`. Valores têm duas casas decimais em strings e datas têm timezone
UTC. O vínculo `pagamento_id` permite associar todos os estornos ao pagamento
original e calcular seu limite restante. Totais e saldo autoritativos continuam
nos campos de resumo existentes.

Não são retornados dados pessoais de operadores, identificadores de operadores,
credenciais, fingerprints ou chaves de idempotência no histórico. Não houve
ampliação de autorização: ADMIN e RECEPCAO respeitam o escopo existente de filial;
BARBEIRO e BARBEIRO_CHEFE continuam restritos às próprias comandas. Falta de
escopo retorna o mesmo 404 de recurso inexistente, sem histórico parcial.

Para `nao_verificado`, `historico` contém as duas listas vazias; somatórios,
líquido e saldo permanecem null. Lista vazia não significa pagamento ou dívida.
Resumo e histórico são materializados sob o mesmo lock compartilhado já usado
pela consulta, que bloqueia as escritas financeiras pelos serviços até encerrar
a transação de leitura. Não são feitos commit, flush ou mutação no GET.
As regras e os DTOs dos POSTs permanecem inalterados.

### POST /comandas/{id}/pagamentos

Schema `PagamentoCreate`:

```json
{"valor":"10.00","forma":"pix","recebido_em":"2026-11-13T10:00:00-03:00"}
```

Todos obrigatórios. `forma`: `dinheiro | pix | debito | credito`.
Endpoint deprecado, mantido somente para replay histórico de pagamento já
existente com a chave e o payload originais. Novos pagamentos avulsos, parciais
ou integrais recebem 409 `estado_financeiro_incompativel`, sem escrita.
Chave existente com outro conteúdo recebe 409 `conflito_idempotencia`.
Autorização e escopo são revalidados antes de revelar o registro original.

Resposta 200 no replay, schema `PagamentoOut`:

```json
{"id":"33333333-3333-4333-8333-333333333333","comanda_id":"11111111-1111-4111-8111-111111111111","filial_id":"22222222-2222-4222-8222-222222222222","valor":"10.00","forma":"pix","recebido_em":"2026-11-13T13:00:00Z","registrado_em":"2026-11-13T13:01:00Z","registrado_por":"44444444-4444-4444-8444-444444444444","chave_idempotencia":"55555555-5555-4555-8555-555555555555"}
```

### POST /comandas/{id}/estornos

Schema `EstornoCreate`, todos obrigatórios:

```json
{"pagamento_id":"33333333-3333-4333-8333-333333333333","valor":"2.00","motivo":"Correção do recebimento","efetivado_em":"2026-11-13T10:30:00-03:00"}
```

Somente ADMIN, atendimento concluído e financeiro aberto. Pagamento deve pertencer
à mesma comanda/filial. Motivo deve ser texto não vazio após trim; data não pode
anteceder o recebimento original. Soma dos estornos não excede o pagamento.
Não apaga nem altera o pagamento; pode reabrir saldo antes do fechamento.
Resposta 200, schema `EstornoOut`: `id`, `pagamento_id`, `comanda_id`, `filial_id`
(UUID), `valor` (string), `motivo` (texto normalizado), `efetivado_em`,
`registrado_em` (timestamps UTC), `registrado_por`, `chave_idempotencia` (UUID).

### POST /comandas/{id}/fechamento-financeiro

Header `Idempotency-Key` UUID obrigatório. Corpo `FechamentoFinanceiroCreate`:

```json
{"pagamentos":[{"valor":"30.00","forma":"pix","recebido_em":"2026-11-15T10:00:00-03:00","confirmado":true},{"valor":"40.00","forma":"dinheiro","recebido_em":"2026-11-15T10:00:00-03:00","confirmado":true}],"motivo":null}
```

Exemplo ilustrativo para saldo de 70.00; usar a data real do recebimento, nunca
futura. Lista de zero a 16 parcelas positivas, com `confirmado` obrigatoriamente
igual ao booleano `true`. A confirmação é declaração do operador autorizado;
não existe conciliação automática com banco ou adquirente.

Exige atendimento concluído, controle verificado e financeiro aberto. Sob lock,
a soma precisa corresponder exatamente ao saldo restante: insuficiência ou
excesso recebe 409 `saldo_insuficiente`. Não permite fiado ou novos pagamentos
parciais. `{}` ou `{"pagamentos":[]}` só fecha saldo já zero; total zero exige
motivo não vazio e não cria pagamento fictício.

Um único commit confirma pagamentos, snapshot financeiro e estado/data da
comanda. Falhas antes da confirmação revertem o conjunto. A resposta 200 é
`FechamentoFinanceiroOut`: `comanda_id`, `filial_id`, `total`,
`recebido_liquido`, `motivo`, `registrado_em`, `registrado_por` e
`chave_idempotencia`. Não aceita total/saldo fornecido pelo cliente.

Replay mantém chave, ordem das parcelas, formas, valores, datas, confirmações e
motivo. Decimais e instantes equivalentes são canônicos; outra composição com
a mesma chave recebe 409. O fingerprint inclui a composição ordenada. As chaves
de cada pagamento são UUIDv5 derivadas da operação e de `comanda_id:índice`.
Outra chave após fechamento recebe 409, sem nova cobrança. Novas operações,
inclusive estorno, ficam bloqueadas; não há reabertura.

### POST /comandas/{id}/itens/servicos

Bearer, `Idempotency-Key` UUID e `filial_id` opcional como restrição adicional:

```json
{"servico_id":"11111111-1111-4111-8111-111111111111","quantidade":2}
```

`InclusaoServicoCreate` rejeita campos extras; quantidade é inteiro estrito de
1 a 999. Serviço precisa existir e estar ativo. O catálogo atual é compartilhado;
o isolamento de filial é aplicado ao contexto da comanda, sem inventar catálogo
de serviços por filial. ADMIN/RECEPCAO operam no escopo autorizado; BARBEIRO e
BARBEIRO_CHEFE somente nas próprias comandas.

Nova inclusão exige comanda operacionalmente `aberta`, financeiro verificado e
aberto, e atendimento não cancelado. Pode ocorrer após conclusão operacional.
Descrição e preço vêm exclusivamente do catálogo sob lock compartilhado; preço
histórico dos itens anteriores não muda. O total canônico é a soma dos itens,
limitado a 99999999.99. Horários, duração e estado do agendamento não mudam.

Item, auditoria e idempotência são confirmados no mesmo commit, com locks na
mesma ordem do fechamento. Requer `e14a29bc7031`, sem backfill histórico.
Resposta 200 em criação e replay, `InclusaoServicoOut`: `item` (incluindo
`subtotal`), `total`, `registrado_em`, `registrado_por`, `chave_idempotencia`.
Valores deste DTO seguem os tipos Decimal dos schemas de comanda; a exigência
de dinheiro textual de entrada aplica-se aos pagamentos, não há preço no body
de inclusão. `total` no replay é o snapshot original; consultar depois para
obter o total atual.

Mesmo serviço/quantidade e chave devolvem o resultado original, mesmo se o
catálogo mudar ou a comanda fechar depois. Outro payload recebe 409. Nova
inclusão após fechamento ou em cancelada recebe 409; legado não verificado,
409 `historico_financeiro_nao_verificado`; serviço inativo/inexistente ou entrada
inválida, 422. Reutiliza ocultação de recurso, sanitização e erros financeiros.
Não existe endpoint de produtos/bebidas nesta funcionalidade.

## Idempotência e resultado incerto

Cliente gera e persiste a chave UUID **antes** do primeiro envio. Após timeout,
perda de conexão ou confirmação indeterminada, repete a mesma operação, comanda,
chave e payload, inclusive o timestamp original. Nunca gerar nova chave para
um recebimento cujo resultado é desconhecido. Não substituir a data por “agora”.
Se o commit ocorreu, o serviço devolve o mesmo registro, identificador e carimbo;
se não ocorreu, pode criar uma única vez, sujeito às regras atuais.

Escopo da chave: operação + comanda (filial está vinculada à comanda).
Payload canônico do pagamento: comanda, valor com duas casas, forma e instante
recebido UTC. Estorno inclui pagamento, valor, motivo após trim e instante UTC;
fechamento inclui comanda, motivo normalizado e composição ordenada dos pagamentos;
inclusão inclui serviço e quantidade. Instantes equivalentes com offsets
diferentes e valores `10.0`/`10.00` têm o mesmo significado. Chave existente com
payload diferente retorna 409 `conflito_idempotencia`, sem nova gravação.
Chave igual em outra operação não deduplica aquela operação.

Replay revalida autenticação, atividade e escopo **antes** de devolver dados.
Um replay válido pode retornar registro anterior mesmo após fechamento ou após
expirar a janela retroativa; não representa uma nova operação. Nova chave após
fechamento recebe 409. Fechamento repetido só retorna sucesso com sua chave
original e payload equivalente. Serialização por lock da comanda protege
requisições simultâneas; a restrição UNIQUE é defesa adicional. A resposta não
promete o mesmo token HTTP nem ignora revogação de acesso.

## Retroatividade

Para novo pagamento não ADMIN, usando o relógio do banco no processamento:
`agora - 168 horas <= recebido_em <= agora`. Os dois limites são inclusivos;
168 horas exatas são aceitas, um microssegundo anterior é recusado (422).
Comparação entre instantes UTC, sem truncar dias nem usar o fuso do cliente;
o serviço usa America/Recife para apresentação do relógio. ADMIN pode lançar
antes de 168 horas, mas nunca no futuro. Estorno é exclusivo ADMIN, sem limite
inferior de 168 horas, respeitando a data do recebimento original. `registrado_em`
é sempre o carimbo real do banco e não pode ser retroagido pelo cliente.

## Erros HTTP

Envelope para estas novas rotas: `{"detail":{"codigo":"saldo_insuficiente","mensagem":"Saldo incompatível com o pagamento ou fechamento"}}`.
Não modificar o envelope de rotas públicas existentes. Validação estrutural
retorna `detail` em lista de mensagens pelo handler existente da aplicação;
ambas as variantes do 422 estão no OpenAPI. Textos de domínio e driver não são
repassados: as mensagens financeiras são fixas por código. Erros de banco nas
dependências, inclusive autenticação, também recebem resposta sanitizada.
Nunca retornar SQL, parâmetros ou texto cru do driver.

| HTTP | Código / condição |
| --- | --- |
| 401 | Credencial ausente/inválida, conforme autenticação existente |
| 403 | `acesso_financeiro_negado` — atividade/perfil, estorno sem ADMIN |
| 404 | `comanda_financeira_nao_encontrada` — recurso ou escopo oculto |
| 422 | `entrada_financeira_invalida` — valor, forma, data, janela, motivo, UUID/header; ou validação estrutural |
| 409 | `historico_financeiro_nao_verificado` — exige conciliação específica |
| 409 | `estado_financeiro_incompativel` — cancelado, não concluído ou já fechado |
| 409 | `saldo_insuficiente` — excesso de recebimento ou saldo no fechamento |
| 409 | `limite_estorno_excedido` |
| 409 | `conflito_idempotencia` |
| 409 | `conflito_persistencia` — somente constraints conhecidas |
| 500 | `dados_financeiros_inconsistentes` — interromper operação, sem corrigir automaticamente |
| 500 | `falha_persistencia` — falha não classificada, sem afirmar rollback/sucesso |
| 503 | `banco_indisponivel` — repetir com mesma chave nas escritas |
| 503 | `transacao_abortada` — rollback confirmado, repetição com mesma chave |
| 503 | `confirmacao_indeterminada` — resultado desconhecido, mesma chave e payload |

## Leitura, histórico e recuperação

O GET retorna o histórico completo autorizado da comanda, inclusive pagamentos
antigos e estornos associados; não existe histórico global ou paginação desse
histórico. A projeção de listagem, os filtros e os indicadores estão documentados
em [interface de comandas](comandas-interface.md). Nunca inferir quitação de um
status operacional ou ativar legado por consulta.

Timeout de inclusão ou fechamento deve preservar a intenção original. Um GET
não elimina a necessidade de replay para resolver a operação incerta. O frontend
coordena pendências no mesmo navegador; o backend serializa pelo estado confirmado
e locks. Não há estado distribuído de incerteza entre dispositivos.

Testes de contrato: `backend/tests/contracts/test_financeiro_http.py`,
`test_fechamento_integral.py` e `test_itens_comanda.py`. Integração real requer
PostgreSQL descartável validado pelo conftest, sem bancos externos. Resultados,
logs e capturas de cada execução são locais, em `.local-qa/`.
