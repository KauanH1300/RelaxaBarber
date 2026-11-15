# Comandas: consulta, serviços e fechamento financeiro

Referência funcional da interface implementada. Contratos de escrita e erros:
[financeiro HTTP](financeiro-mvp-http.md). Transações e locks:
[serviços financeiros](financeiro-mvp-servicos.md). Esta documentação não
autoriza implantação nem execução de migrações.

## Consulta e apresentação

A página `/comandas` usa dados reais da filial ativa. Pesquisa por cliente ou
UUID, profissional e intervalo de datas são aplicados no servidor. Percentuais
e sublinhados da busca são literais. O UUID curto é apenas apresentação; todas
as operações usam o UUID completo. Respostas de contexto de filial anterior são
descartadas pelo frontend.

- `GET /comandas/painel`: paginação (`pagina` inicial 1, `tamanho` inicial 6,
  máximo 48), `busca` até 100 caracteres, `status` operacional,
  `status_financeiro` de apresentação, `profissional_id`, `data_inicio`,
  `data_fim` e `filial_id`.
- `GET /comandas/{id}`: pessoas, atendimento, filial, itens e projeção financeira.
- `GET /comandas`: consulta compatível, com filtro operacional `status`.

O período inicial é o dia atual em America/Recife. Datas inicial e final são
inclusivas. Para apresentação `fechada`, o período considera o instante do
fechamento financeiro convertido ao dia civil em Recife; para as demais,
considera a data do atendimento. A ordem do painel é criação decrescente,
desempatada pelo UUID. A paginação usa limite e deslocamento no banco.

## Estados e indicadores

`status` operacional é preservado, inclusive em registros históricos. Não deve
ser usado isoladamente como prova de pagamento. A interface usa
`status_apresentacao`, `saldo_financeiro` e `fechamento_financeiro_em`:

| Apresentação | Significado |
| --- | --- |
| `pendente` / `aberta` | Reserva/atendimento ainda em operação, com financeiro verificado. |
| `pagamento_pendente` | Atendimento concluído e saldo positivo verificado. |
| `aguardando_fechamento` | Quitação comprovada, mas sem fechamento financeiro; também abrange total zero verificado. |
| `fechada` | Fechamento financeiro existente, saldo zero e snapshot coerente com itens e recebido líquido. |
| `nao_verificado` | Sem controle financeiro ou com inconsistência; exibir “Pagamento não verificado”, sem inferir dívida ou quitação. |
| `cancelada` | Cancelamento operacional preservado. |
| `restrito` | Sem autorização para a classificação financeira daquele atendimento. |

Os indicadores são calculados no servidor antes dos filtros de status e da
paginação, respeitando busca, profissional, período e autorização:

- **Comandas abertas**: `aberta`, `pagamento_pendente` e `aguardando_fechamento`
  verificados; não inclui reserva `pendente` nem legado não verificado.
- **Aguardando pagamento**: quantidade em `pagamento_pendente`.
- **Fechadas no período**: apenas `fechada` comprovada, pela data financeira.
- **Valor em aberto** (`valor_abertas`): soma dos saldos verificados dos estados
  abertos acima; não soma o total bruto de itens nem presume dívida do legado.

`contagens` mantém os estados operacionais por compatibilidade;
`contagens_apresentacao` contém a classificação financeira. Itens, pagamentos
e estornos são pré-agregados por comanda antes dos joins, evitando duplicações.
As consultas não ativam, conciliam, corrigem ou modificam dados históricos.

## Permissões

ADMIN e RECEPCAO têm o escopo financeiro das filiais autorizadas. BARBEIRO e
BARBEIRO_CHEFE operam somente suas próprias comandas. A leitura operacional
mais ampla do chefe não concede leitura financeira de terceiros: a projeção
usa `restrito`, sem saldo ou data financeira, e os agregados financeiros
consideram apenas o escopo próprio (`escopo_financeiro=proprias`). O backend
revalida todas as operações; filtros não ampliam permissões.

## Layout e inclusão de serviços

Identidade escura e dourada, com ações principais em `#e5b044`. Listagem e cards
seguem a linguagem do protótipo Stitch; detalhe e financeiro são adaptações
funcionais. O HTML original não apresenta uma tela de pagamento equivalente.
Não apresentar VIP, créditos, descontos, impressão fiscal ou catálogo fictício.

O detalhe contém cliente, profissional, informações do atendimento, tabela de
itens e financeiro. A tabela apresenta descrição, categoria, quantidade, valor
unitário e subtotal, com **Adicionar serviço** abaixo dela. O formulário consulta
serviços cadastrados e ativos, mostra preço/subtotal de referência e quantidade.
Preço, descrição e total definitivos são calculados no backend. Itens anteriores
mantêm o preço histórico. Incluir serviço não modifica duração, horários ou
estado do agendamento. Não há ação de produtos/bebidas: o catálogo não existe.

É possível incluir em comanda operacionalmente aberta e financeiramente
verificada, inclusive depois de concluir o atendimento e antes de fechar a
comanda. Comandas fechadas, canceladas ou não verificadas são bloqueadas. Uma
intenção financeira incerta na interface bloqueia nova inclusão, e uma inclusão
incerta bloqueia novo fechamento até recuperação. No servidor, as operações
compartilham locks e revalidam o estado confirmado; não existe reserva persistente
de “incerteza” entre dispositivos.

## Pagamento e recuperação

O resumo principal destaca **Valor Total** e **Valor Recebido**, líquido de
estornos. Atendimento concluído não equivale a comanda fechada. A interface
compõe de 1 a 16 recebimentos confirmados (PIX, dinheiro, débito ou crédito),
com soma exatamente igual ao restante, e envia um único fechamento atômico.
Alterar valor, forma ou data exige confirmar novamente a parcela. Não há novos
pagamentos parciais, saldo futuro ou fiado. Quitação anterior permite fechar sem
novos pagamentos; total zero exige motivo auditável.

Histórico vem do GET persistido, inclusive após reabrir o detalhe. Não há lista
otimista paralela: após inclusão ou fechamento, recarregar itens, detalhe,
resumo/histórico e indicadores. Uma falha nessa atualização não desfaz o POST
confirmado nem deve sugerir repetir com outra chave.

Antes de enviar, persistir chave e payload no `sessionStorage`, com escopo de
usuário, filial e comanda. Bloquear cliques repetidos e mostrar loading. Timeout,
falha de transporte ou confirmação indeterminada conservam a intenção: recuperar
com a mesma chave e conteúdo, sem alterar datas, ordem ou composição. Um GET
sozinho não confirma nem apaga a intenção. Falha de armazenamento antes do envio
bloqueia o POST; conteúdo corrompido não deve ser apagado silenciosamente.

O replay de inclusão devolve o item e o total da operação original; uma consulta
posterior obtém o total atual. O replay financeiro não cria novas cobranças.
Recuperação antiga de `/pagamentos` conserva a operação original, sem convertê-la
automaticamente em fechamento. `sessionStorage` não garante recuperação após
fechar a aba, limpar o armazenamento ou mudar de dispositivo.

Estorno novo exige ADMIN, financeiro aberto e limite restante do pagamento.
Financeiro fechado não aceita novas movimentações; não há reabertura. Falhas de
acesso usam o tratamento existente de sessão/filial e ocultação de recurso.

## Responsividade, acessibilidade e testes

Manter diálogo utilizável em desktop, tablet e celular, inclusive 320 px;
rolagem acessível da tabela, sem cortar formulário, ações ou mensagens. Preservar
rótulos, foco inicial, contenção de Tab/Shift+Tab, Escape e retorno do foco.
Não depender apenas da cor para estados, erros ou confirmação.

Os testes reproduzíveis ficam em `frontend/tests/*.test.mjs`,
`comandas.browser.mjs`, `financeiro.browser.mjs`, `homologacao-etapa3.browser.mjs`
e `homologacao-etapa4.browser.mjs`. Usar o executor
`frontend/tests/helpers/validarFrontend.cjs` e os Dockerfiles de testes conforme
o ambiente preparado. Backend: testes em `backend/tests` e
`backend/integration_tests`, incluindo `test_itens_comanda.py` e
`test_fechamento_integral.py`. Integração requer PostgreSQL descartável com
identidade validada pelo conftest, sem bancos externos. Resultados de execução,
capturas e logs devem ficar em `.local-qa/`, sem versionamento.

Com dependências preparadas, executar no diretório `frontend`:

```sh
node --test tests/*.test.mjs
npm run lint
npm run build
node tests/comandas.browser.mjs
node tests/financeiro.browser.mjs
```

As suítes de navegador acima usam API simulada e não comprovam persistência real.
Requerem Node 22+ e Firefox; `FIREFOX_BIN` seleciona o executável e
`COMANDAS_SCREENSHOT_DIR` pode apontar para diretório local ignorado já existente.
Para integração real, usar os executores de homologação e o ambiente descartável
validado, sem carregar `.env` ou credenciais de produção. As fixtures PostgreSQL
recriam schema; nunca executar a suíte contra banco persistente.
