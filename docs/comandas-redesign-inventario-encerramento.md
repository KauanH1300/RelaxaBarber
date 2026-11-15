# Inventário de encerramento — redesign de comandas

Data: 15/11/2026. Branch `feat/comandas-redesign-stitch`, HEAD `a69223b`.
**Proposta para autorização: 50 arquivos em três commits. Nenhum arquivo foi
adicionado ao índice; nenhum commit ou push foi executado.**

Foram lidos os relatórios da Etapa 4 e da homologação integrada. `git status`,
`git diff --stat` e `git diff --check` executados: sem erros de whitespace;
apenas avisos de normalização LF/CRLF. O diff rastreado contém seis arquivos:
quatro do trabalho atual (três da interface e um teste) e os dois preexistentes
`frontend/package.json`/`frontend/src/assets/logo.png`, que ficam fora.
O novo teste e documentos/evidências ainda são não rastreados.

## Commit 1 — interface (3 arquivos)

Mensagem proposta:
`feat(comandas): adaptar interface ao Stitch com financeiro responsivo e foco acessivel`

Inclui layout, dourado #e5b044, cards de cliente/profissional, informações,
serviços, painel financeiro e correção do ciclo de foco nas seções recolhidas.

```text
frontend/src/pages/comandas/Comandas.css
frontend/src/pages/comandas/DetalheComanda.tsx
frontend/src/pages/comandas/FinanceiroComanda.tsx
```

## Commit 2 — testes (2 arquivos)

Mensagem proposta:
`test(comandas): cobrir redesign responsivo e homologacao integrada isolada`

Inclui capturas, testes de responsividade/teclado e extensão da suíte integrada
existente. O executor não inicializa banco nem executa migrações; requer o
ambiente descartável previamente autorizado/preparado. Preserva os testes de
pagamentos combinados, confirmação incerta, timeout, replay, perfis e filial.

```text
frontend/tests/financeiro.browser.mjs
frontend/tests/homologacao-etapa4.browser.mjs
```

## Commit 3 — documentação e evidências (45 arquivos)

Mensagem proposta:
`docs(comandas): registrar redesign e homologacao integrada com evidencias revisadas`

Lista exata, incluindo este inventário. Os links dos três relatórios têm seus
arquivos de destino incluídos; não há dependência de captura excluída para abrir
os links Markdown. Referências textuais a diagnósticos `tentativa*`, snapshots e
pastas temporárias descrevem material local, que não fará parte do commit.

```text
docs/comandas-etapa4-redesign-stitch.md
docs/comandas-homologacao-final-integrada-stitch.md
docs/comandas-homologacao-final-stitch.md
docs/comandas-redesign-inventario-encerramento.md
docs/qa-comandas-etapa4/browser-checks.txt
docs/qa-comandas-etapa4/comandas-desktop.png
docs/qa-comandas-etapa4/comandas-mobile.png
docs/qa-comandas-etapa4/comandas-tablet.png
docs/qa-comandas-etapa4/confirmacao-combinada.png
docs/qa-comandas-etapa4/detalhe-desktop.png
docs/qa-comandas-etapa4/detalhe-mobile.png
docs/qa-comandas-etapa4/detalhe-tablet.png
docs/qa-comandas-etapa4/financeiro-desktop.png
docs/qa-comandas-etapa4/financeiro-mobile.png
docs/qa-comandas-etapa4/financeiro-tablet.png
docs/qa-comandas-etapa4/frontend-checks.txt
docs/qa-comandas-etapa4/stitch-original-desktop.png
docs/qa-comandas-homologacao-final/detalhe-simulado-desktop.png
docs/qa-comandas-homologacao-final/financeiro-simulado-celular.png
docs/qa-comandas-homologacao-final/financeiro-simulado-celular-estreito.png
docs/qa-comandas-homologacao-final/financeiro-simulado-tablet.png
docs/qa-comandas-homologacao-final/frontend-checks.txt
docs/qa-comandas-homologacao-final/integrada/browser-real-checks.txt
docs/qa-comandas-homologacao-final/integrada/detalhe-real-celular.png
docs/qa-comandas-homologacao-final/integrada/detalhe-real-desktop.png
docs/qa-comandas-homologacao-final/integrada/detalhe-real-tablet.png
docs/qa-comandas-homologacao-final/integrada/encerramento.txt
docs/qa-comandas-homologacao-final/integrada/fechada-real-desktop.png
docs/qa-comandas-homologacao-final/integrada/financeiro-real-celular.png
docs/qa-comandas-homologacao-final/integrada/financeiro-real-celular-estreito.png
docs/qa-comandas-homologacao-final/integrada/frontend-checks.txt
docs/qa-comandas-homologacao-final/integrada/homologacao.json
docs/qa-comandas-homologacao-final/integrada/identidade-runtime.txt
docs/qa-comandas-homologacao-final/integrada/isolamento-executores.txt
docs/qa-comandas-homologacao-final/integrada/isolamento-pg.txt
docs/qa-comandas-homologacao-final/integrada/lint-final.txt
docs/qa-comandas-homologacao-final/integrada/pagamentos-combinados-reais.png
docs/qa-comandas-homologacao-final/integrada/painel-real-topo-celular.png
docs/qa-comandas-homologacao-final/integrada/painel-real-topo-desktop.png
docs/qa-comandas-homologacao-final/integrada/painel-real-topo-tablet.png
docs/qa-comandas-homologacao-final/integrada/persistencia-final.txt
docs/qa-comandas-homologacao-final/integrada/preservacao-final.json
docs/qa-comandas-homologacao-final/integrada/sem-env-sem-saida.txt
docs/qa-comandas-homologacao-final/layout-simulado-checks.txt
docs/qa-comandas-homologacao-final/stitch-original-desktop.png
```

## Revisão de segurança e escopo

- Os 43 arquivos anteriores foram comparados com o manifesto SHA-256 original:
  todos presentes e idênticos; nenhum consta das listas de commits acima.
- Backend e `frontend/src/services` estão idênticos a HEAD. Não há mudanças em
  migrações, schemas financeiros, endpoints, tipos/contratos de serviço ou lógica
  de envio/recuperação. As mudanças no financeiro são de marcação e classes CSS.
- Não foram encontrados JWTs, tokens Bearer literais, chaves de provedores,
  chaves privadas, URLs de banco com senha ou atribuições literais de credenciais
  nos textos selecionados e na referência. Não há `.env`, dumps, backups,
  arquivos temporários, bundles ou configurações locais na seleção.
- Os `.txt` selecionados são evidências finais revisadas (checks, resultado SQL,
  isolamento e encerramento). `persistencia-final.txt` contém resultados de
  consultas de fixtures descartáveis: não é dump de banco nem schema SQL.
  UUIDs e chaves de idempotência são da massa fictícia de teste, não tokens.
- As 26 capturas selecionadas mostram a referência estática ou fixtures dos
  testes locais. Não há chunks PNG textuais/EXIF nos arquivos selecionados.
  A inspeção de padrões não é garantia absoluta de ausência de informação
  sensível; foi combinada com revisão de conteúdo, origem e imagens já avaliadas
  na homologação.
- `ref/comandas.html` foi revisado: sem indicadores de credenciais, endpoints
  privados, e-mails ou contatos pessoais identificados. Contém nomes e consumo
  apresentados como exemplos do protótipo e URLs externas de recursos públicos
  de Tailwind/Google Fonts/Googleusercontent. O único base64 é um SVG placeholder,
  sem conteúdo sensível identificado. Continua ignorado e não será forçado para
  o Git; a captura da referência é suficiente para a documentação proposta.
- O índice Git permanece vazio. Não foram executados testes, migrações, Docker,
  acesso a banco/Supabase ou operações destrutivas nesta auditoria. As evidências
  de aprovação são as da homologação anterior; não se afirma uma nova execução.

## Arquivos originais excluídos dos commits (43)

Preservados integralmente. Esta exclusão é explícita, inclusive para o package
modificado e a logo, sem `git add .` ou inclusão de diretórios inteiros.

```text
backend/scripts/qa_financeiro_login_leitura.py
backend/scripts/qa_financeiro_persistencia_leitura.py
backend/scripts/qa_financeiro_precondicoes.py
backend/scripts/qa_financeiro_preservacao.py
backend/scripts/qa_financeiro_retomada_leitura.py
backend/scripts/seguranca_etapa13_leitura.py
docs/financeiro-etapa12-retomada.md
docs/financeiro-etapa12-validacao.md
docs/financeiro-etapa13-seguranca.md
docs/financeiro-etapa14-perfis.md
docs/financeiro-etapa14-retomada.md
docs/qa-etapa3-isolada/aprovacao-parcial-antes-ui-agenda.json
docs/qa-etapa3-isolada/diagnostico-tentativa4.png
docs/qa-etapa3-isolada/diagnostico-tentativa4.txt
docs/qa-etapa3-isolada/fechamento-combinado.png
docs/qa-etapa3-isolada/frontend-checks.txt
docs/qa-etapa3-isolada/homologacao.json
docs/qa-etapa3-isolada/identidade-e-contagens.json
docs/qa-etapa3-isolada/isolamento-aplicacao.txt
docs/qa-etapa3-isolada/isolamento-postgresql.txt
docs/qa-etapa3-isolada/persistencia-final.txt
docs/qa-etapa3-isolada/postgresql-testes.txt
docs/qa-etapa3-isolada/preservacao-final.json
docs/qa-etapa3-isolada/prova-sem-env-sem-saida.txt
docs/qa-etapa3-isolada/seed-ficticio.json
docs/qa-etapa3-isolada/tentativa1.json
docs/qa-etapa3-isolada/tentativa2.json
docs/qa-etapa3-isolada/tentativa3.json
docs/qa-etapa3-isolada/tentativa4.json
docs/qa-financeiro-20261113/financeiro-real-desktop-fechado.png
docs/qa-financeiro-20261113/financeiro-real-mobile-fechado.png
docs/qa-financeiro-20261113/fluxo-real.json
docs/qa-financeiro-20261113/persistencia-supabase.json
docs/qa-financeiro-20261113/preservacao-final.json
docs/qa-financeiro-20261113/preservacao-inicial.json
docs/qa-perfis-20261113/preservacao-final.json
docs/qa-perfis-20261113/preservacao-inicial.json
frontend/package.json
frontend/src/assets/logo.png
frontend/tests/financeiro.supabase.mjs
frontend/tests/helpers/executarQaPerfis.cjs
frontend/tests/helpers/executarQaReal.cjs
frontend/tests/perfis.supabase.mjs
```

## Artefatos adicionais do trabalho mantidos somente locais

Além da referência ignorada `ref/comandas.html`, os arquivos abaixo pertencem às
execuções de QA, mas ficam fora da proposta: capturas redundantes/não vinculadas,
logs brutos, provisionamento/seed, diagnósticos e tentativas incompletas.
Nenhum deles foi removido ou alterado.

```text
docs/qa-comandas-etapa4/financeiro-browser-checks.txt
docs/qa-comandas-etapa4/reference-checks.txt
docs/qa-comandas-homologacao-final/browser-simulado-checks.txt
docs/qa-comandas-homologacao-final/comandas-desktop.png
docs/qa-comandas-homologacao-final/comandas-mobile.png
docs/qa-comandas-homologacao-final/comandas-tablet.png
docs/qa-comandas-homologacao-final/confirmacao-combinada.png
docs/qa-comandas-homologacao-final/detalhe-desktop.png
docs/qa-comandas-homologacao-final/detalhe-mobile.png
docs/qa-comandas-homologacao-final/detalhe-simulado-celular.png
docs/qa-comandas-homologacao-final/detalhe-simulado-celular-estreito.png
docs/qa-comandas-homologacao-final/detalhe-simulado-tablet.png
docs/qa-comandas-homologacao-final/detalhe-tablet.png
docs/qa-comandas-homologacao-final/financeiro-desktop.png
docs/qa-comandas-homologacao-final/financeiro-mobile.png
docs/qa-comandas-homologacao-final/financeiro-simulado-desktop.png
docs/qa-comandas-homologacao-final/financeiro-tablet.png
docs/qa-comandas-homologacao-final/historico-simulado-celular.png
docs/qa-comandas-homologacao-final/historico-simulado-celular-estreito.png
docs/qa-comandas-homologacao-final/historico-simulado-desktop.png
docs/qa-comandas-homologacao-final/historico-simulado-tablet.png
docs/qa-comandas-homologacao-final/integrada/api-log.txt
docs/qa-comandas-homologacao-final/integrada/capturas-adicionais.txt
docs/qa-comandas-homologacao-final/integrada/containers-apos-encerramento.txt
docs/qa-comandas-homologacao-final/integrada/detalhe-real-celular-estreito.png
docs/qa-comandas-homologacao-final/integrada/fechamento-combinado.png
docs/qa-comandas-homologacao-final/integrada/financeiro-real-desktop.png
docs/qa-comandas-homologacao-final/integrada/financeiro-real-tablet.png
docs/qa-comandas-homologacao-final/integrada/historico-real-celular.png
docs/qa-comandas-homologacao-final/integrada/historico-real-celular-estreito.png
docs/qa-comandas-homologacao-final/integrada/historico-real-desktop.png
docs/qa-comandas-homologacao-final/integrada/historico-real-tablet.png
docs/qa-comandas-homologacao-final/integrada/listagem-real-celular.png
docs/qa-comandas-homologacao-final/integrada/listagem-real-celular-estreito.png
docs/qa-comandas-homologacao-final/integrada/listagem-real-desktop.png
docs/qa-comandas-homologacao-final/integrada/listagem-real-tablet.png
docs/qa-comandas-homologacao-final/integrada/provisionamento.txt
docs/qa-comandas-homologacao-final/integrada/seed-ficticio.json
docs/qa-comandas-homologacao-final/integrada/tentativa1.json
docs/qa-comandas-homologacao-final/integrada/tentativa1-checks.txt
docs/qa-comandas-homologacao-final/integrada/tentativa2.json
docs/qa-comandas-homologacao-final/integrada/tentativa2-checks.txt
docs/qa-comandas-homologacao-final/integrada/ultima-pagina.png
docs/qa-comandas-homologacao-final/integrada/ultima-pagina.txt
docs/qa-comandas-homologacao-final/listagem-simulado-celular.png
docs/qa-comandas-homologacao-final/listagem-simulado-celular-estreito.png
docs/qa-comandas-homologacao-final/listagem-simulado-desktop.png
docs/qa-comandas-homologacao-final/listagem-simulado-tablet.png
docs/qa-comandas-homologacao-final/reference-checks.txt
```

## Revisão após autorização condicional

A revisão adicional encontrou um par idêntico byte a byte:
`docs/qa-comandas-etapa4/browser-checks.txt` e
`docs/qa-comandas-homologacao-final/browser-simulado-checks.txt`.
A proposta mantém o primeiro, exclui o segundo do versionamento e ajusta o link
no relatório parcial, registrando a consolidação. Os dois arquivos originais
continuam intactos localmente. Nenhum outro caminho da seleção foi alterado.
A lista passou de 51 para **50 arquivos: 3 + 2 + 45**.

As mensagens de commit permanecem as mesmas. Esta seleção revisada requer nova
confirmação do usuário, conforme a condição 4 da autorização. Nenhum commit foi
criado e nenhum arquivo foi adicionado ao índice nesta revisão.

## Próximo passo

Aguardar autorização explícita para os três commits e sua seleção exata.
Push continua fora do escopo. Antes de qualquer commit autorizado, conferir
novamente branch, hashes dos arquivos originais e o diff do índice contendo
somente os arquivos deste inventário.