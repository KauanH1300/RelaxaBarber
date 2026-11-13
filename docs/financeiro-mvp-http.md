# Financeiro MVP — ativação e contratos HTTP

Status: endpoints e schemas Pydantic implementados na etapa 5. O contrato preparado
na etapa 4 permanece a referência; os schemas públicos de agendamento e comanda
não foram alterados. As rotas estão no módulo `app/api/routes/financeiro.py` e
registradas na aplicação principal, com documentação automática em `/openapi.json`
e `/docs` (tag Financeiro).

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
Não é necessária alteração de schema. Essa revisão precisa existir no banco antes
de executar este código; permanece **não aplicada no Supabase** nesta entrega.

Ausência de controle continua significando `nao_verificado`. Nenhuma comanda
antiga é ativada, declarada paga ou classificada como devedora. Conciliação será
um fluxo específico auditado; nem ADMIN pode contornar esse bloqueio.

Os estados operacionais permanecem: comanda `pendente`, depois `aberta`,
`fechada` quando agendamento chega a `concluido`, ou `cancelada` no cancelamento.
`data_fechamento` é operacional. A conclusão não cria pagamento ou fechamento
financeiro: a situação financeira continua `aberto`, inclusive com valor zero.
Cancelamento também mantém o controle aberto e auditável; não gera dívida
exigível nem permite pagamento, pois falta conclusão operacional. Relatórios
futuros devem considerar o estado operacional, não só saldo ou situação financeira.

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

Sem body. Resposta 200, schema `ResumoFinanceiroOut`:

```json
{"comanda_id":"11111111-1111-4111-8111-111111111111","filial_id":"22222222-2222-4222-8222-222222222222","situacao":"aberto","total":"30.50","pagamentos":"10.00","estornos":"0.00","recebido_liquido":"10.00","saldo":"20.50"}
```

`situacao`: `nao_verificado | aberto | fechado`. `pagamentos` e `estornos` são
somatórios, não listas. Para legado, esses dois campos, `recebido_liquido` e
`saldo` são **null**; `total` permanece o total dos itens, sem afirmar dívida.
GET não ativa, concilia ou movimenta registros. Não oferece listagem global.

### POST /comandas/{id}/pagamentos

Schema `PagamentoCreate`:

```json
{"valor":"10.00","forma":"pix","recebido_em":"2026-11-13T10:00:00-03:00"}
```

Todos obrigatórios. `forma`: `dinheiro | pix | debito | credito`.
Somente após `agendamento.status=concluido` e `comanda.status=fechada`, com
controle ativo e financeiro aberto. Aceita pagamentos parciais e múltiplas formas;
valor não pode exceder o saldo atual, recalculado dos itens sob lock.
Pagamento que zera saldo não fecha financeiramente.

Resposta 200 tanto na criação quanto no replay (decisão para não exigir alteração
do retorno atual do serviço), schema `PagamentoOut`:

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

Schema `FechamentoFinanceiroCreate`: `{"motivo":null}`; motivo opcional,
mas obrigatório e não vazio após trim quando total é zero. `{}` também aceito
para total positivo. Nenhum campo de valor ou data efetiva recebido.

Atendimento concluído, financeiro aberto, saldo exatamente zero. Zero não exige
pagamento fictício. Após fechamento, novas operações são bloqueadas; não existe
reabertura nesta etapa. Resposta 200, schema `FechamentoFinanceiroOut`:
`comanda_id`, `filial_id` (UUID), `total`, `recebido_liquido` (strings decimais),
`motivo` (texto ou null), `registrado_em` (UTC), `registrado_por` e
`chave_idempotencia` (UUID). Fechamento não muda estados operacionais.

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
fechamento inclui comanda e motivo normalizado. Instantes equivalentes com offsets
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

## Próxima etapa

Planejar separadamente a aplicação autorizada da migração e a integração dos
consumidores destes endpoints. Cliente deve persistir chave e payload até resolver
um resultado incerto. O painel operacional existente continua com
`pagamentos_disponiveis=false`: habilitação de interface não faz parte desta etapa.
Conciliação de legado e eventual reabertura exigem desenho próprio.

## Implementação da etapa 5

- `app/schemas/financeiro.py`: requests com `extra=forbid`, dinheiro textual
  convertido diretamente para Decimal, timestamps com offset e respostas monetárias
  textuais com duas casas, normalizadas para UTC.
- `app/api/routes/financeiro.py`: quatro adaptadores para os serviços existentes,
  sem consultas próprias, cálculos, autorização duplicada, commits ou rollback.
- `app/api/financeiro_errors.py`: APIRoute restrita ao financeiro para mapear erros
  de domínio/persistência, inclusive em dependências. Rotas existentes mantêm seus
  handlers. Erro de programação do banco permanece 500; não vira conflito financeiro.
- Respostas 200 em criação e replay. Nenhum novo schema de banco ou alteração nos
  serviços transacionais. Não houve acesso ao Supabase, alteração de .env/DATABASE_URL,
  frontend, commit ou push.

Exemplos de bodies (substituir os instantes pelo recebimento/estorno real, sem futuro):

```http
GET /comandas/{comanda_id}/financeiro?filial_id={filial_id}
Authorization: Bearer <token>
```

```http
POST /comandas/{comanda_id}/pagamentos
Authorization: Bearer <token>
Idempotency-Key: 55555555-5555-4555-8555-555555555555
Content-Type: application/json

{"valor":"10.00","forma":"pix","recebido_em":"2026-11-13T10:00:00-03:00"}
```

```http
POST /comandas/{comanda_id}/estornos
Authorization: Bearer <token-admin>
Idempotency-Key: 66666666-6666-4666-8666-666666666666
Content-Type: application/json

{"pagamento_id":"33333333-3333-4333-8333-333333333333","valor":"2.00","motivo":"Correção","efetivado_em":"2026-11-13T10:30:00-03:00"}
```

```http
POST /comandas/{comanda_id}/fechamento-financeiro
Authorization: Bearer <token>
Idempotency-Key: 77777777-7777-4777-8777-777777777777
Content-Type: application/json

{"motivo":"Cortesia autorizada"}
```

Para total positivo quitado, fechamento aceita `{}`. O motivo do exemplo é
obrigatório quando o total é zero. Conclusão operacional continua separada.

## Validação da etapa 5

- Suíte backend completa: **833 aprovados** em 112,21 s, incluindo **67 testes
  novos de contrato HTTP**, executada em container `network none`, sem banco externo.
- Integração PostgreSQL: **207 cenários distintos aprovados**, dos quais **44 HTTP**
  novos e os **163 cenários de regressão da etapa 4**. Execução inicial de 205
  cenários em 312,44 s; depois, 2 cenários adicionais de isolamento e revogação
  em 7,56 s, com 42 testes HTTP já executados desmarcados nesse segundo comando.
- HTTP usa a aplicação principal, autenticação JWT real, sessão por requisição e
  login `relaxabarber_dev_app` sem superuser/BYPASSRLS. Não substitui autorização,
  cálculo ou persistência por mocks nos testes PostgreSQL. O relógio do serviço é
  fixado apenas nos casos de fronteira temporal para testar 168 horas exatas e
  um microssegundo fora do limite, sem dependência da duração do teste.
- Cobertura HTTP: quatro perfis, falta de autenticação/token inválido, filial e
  profissional, revogação com JWT anterior, pagamentos parciais/integrais, centavos,
  inválidos/excedentes, timezone, retroatividade/ADMIN/futuro, replay canônico,
  conflito de payload, estorno ADMIN, limites, fechamento explícito, total zero,
  legado com campos null, mapa de erros e OpenAPI. Pagamento externo real retorna
  o mesmo 404 de inexistente no estorno; revogação impede replay de operações.
- Resultado incerto: testes HTTP simulam perda da confirmação após commit real e
  indisponibilidade anterior à escrita. Reenvio com a mesma chave/payload mantém
  um único pagamento. Falhas reais de commit e concorrência permanecem cobertas
  pela suíte de serviços PostgreSQL da regressão.
- Contagem de commits observada no engine: consulta faz zero; pagamento faz um.
  Testes de contrato também verificam que o adaptador não chama commit/begin/rollback.
- PostgreSQL **17.11**, container exclusivo `rb-etapa5-pg`, `network none`, portas
  publicadas `{}`, dados em tmpfs. Executor compartilha somente a rede desse container,
  com backend montado somente leitura. O conftest valida o destino exclusivo
  `127.0.0.1:55432/relaxabarber_concorrencia_test` antes de recriar qualquer schema.
  Nenhum .env foi carregado, DATABASE_URL alterado ou banco remoto acessado.
- Containers e imagem exclusivos da validação removidos após os testes; recursos
  Docker preexistentes preservados. Hashes SHA256 do frontend permaneceram iguais:
  `package.json`: `E3894A862473B3CC1E775E75F4D1333A92844A4D9376B13D7F40ACB4A4FB52B1`;
  `logo.png`: `5744331DF85257A3E1D70A2B760C4C243A86DCA5DD2B3C62D1B1F2794CF8DF40`.

Comandos pytest no executor isolado, com diretório de trabalho `backend`:

```text
python -m pytest tests -q -p no:cacheprovider
python -m pytest integration_tests/test_financeiro_http.py integration_tests/test_financeiro_ativacao.py integration_tests/test_financeiro_servicos.py integration_tests/test_financeiro_persistencia.py integration_tests/test_cancelamento_etapa_g.py integration_tests/test_concorrencia.py -q -p no:cacheprovider
python -m pytest integration_tests/test_financeiro_http.py -k "outra_comanda_filial or revogacao_admin" -q -p no:cacheprovider
```

## Validação da etapa 4

- PostgreSQL 17.11: **163 testes aprovados** em 252,46 s — 8 novos de ativação,
  73 de serviços, 51 de persistência e 31 de cancelamento/concorrência.
- Os novos testes exercitam criação real com login runtime sem superpoderes,
  um único commit, auditoria e filial, valor zero, falha ao inserir controle,
  falha ao inserir itens, falha após flush completo antes do commit, cancelamento,
  conclusão sem movimentação financeira, pagamento após conclusão e legado intacto.
- Regressão backend separada: **766 aprovados** em 106,46 s, sem rede.
- PostgreSQL em container exclusivo com `network none`, sem portas publicadas,
  dados em tmpfs. Executor com `network container:rb-etapa4-pg`, backend somente
  leitura, sem carregar .env e sem alterar DATABASE_URL. O conftest valida URL,
  porta 55432, banco e usuário exclusivos antes de qualquer conexão destrutiva.
- Seleção de integração: `test_financeiro_ativacao.py`,
  `test_financeiro_servicos.py`, `test_financeiro_persistencia.py`,
  `test_cancelamento_etapa_g.py` e `test_concorrencia.py`, em `integration_tests/`,
  executados com `python -m pytest ... -q -p no:cacheprovider`.
  Regressão: `python -m pytest tests -q -p no:cacheprovider`, em outro processo.
- Nenhum endpoint, migração remota, alteração de frontend, .env, commit ou push.
  Recursos Docker exclusivos desta validação foram removidos após a execução.
