# Etapa 4 — redesign de comandas com referência Stitch

> Documento histórico de implementação, mantido para revisão; descrições e
> pendências abaixo refletem sua etapa, não o estado atual do sistema.
> Referências técnicas atuais: [interface](comandas-interface.md),
> [contratos HTTP](financeiro-mvp-http.md), [transações](financeiro-mvp-servicos.md)
> e [persistência](financeiro-mvp-persistencia.md).
> Evidências de execução são locais e não integram a documentação versionada.


Data: 15/11/2026. Branch: `feat/comandas-redesign-stitch`, baseada em `a69223b`.
Implementação local para revisão; nenhum commit, push ou merge realizado.

## Referência e análise

Original encontrado em `ref/comandas.html`, ignorado pelo Git. O arquivo foi
preservado. Ele apresenta a listagem com quatro indicadores, busca, filtros,
abas, grade de três cards, paginação e aviso inferior. Não contém uma tela
detalhada de pagamento: os detalhes e o financeiro receberam uma adaptação da
mesma linguagem visual, sem alegar correspondência a uma tela inexistente.

Antes desta etapa já existiam listagem, filtros por cliente/identificação,
profissional e período, paginação, visualização em lista, detalhes, itens,
histórico e fluxo financeiro completo. Foram reutilizados os componentes,
tipos, consultas, permissões e contratos existentes. A mudança é de apresentação.

## Arquivos alterados nesta etapa

| Arquivo | Alteração |
| --- | --- |
| `frontend/src/pages/comandas/Comandas.css` | Superfícies, indicadores, cards e ações alinhados ao original; botões principais `#e5b044`; detalhes amplos com duas colunas no desktop; resumo financeiro destacado e adaptação para tablet/celular. |
| `frontend/src/pages/comandas/DetalheComanda.tsx` | Cards de cliente e profissional, seções de informações e serviços, organização do detalhe junto ao financeiro. Mantidos diálogo, foco, Escape, consultas e atualização após confirmação. |
| `frontend/src/pages/comandas/FinanceiroComanda.tsx` | Apresentação da situação financeira, organização dos campos de cada recebimento e destaque do botão de confirmação. Nenhuma mudança na lógica de envio ou recuperação. |
| `frontend/tests/financeiro.browser.mjs` | Verificações de responsividade do diálogo, presença dos cards, cor da ação principal e capturas do resumo e da confirmação combinada. |
| Este relatório e `docs/qa-comandas-etapa4/` | Evidências e resultados da validação. |

`frontend/package.json` e `frontend/src/assets/logo.png` já estavam modificados
antes desta etapa e **não foram alterados por este trabalho**. Nenhuma dependência
adicionada. Backend, banco, serviços e contratos HTTP permaneceram sem alterações.

## Comparação visual e diferenças justificadas

Comparação feita com o HTML original renderizado em Firefox, com Tailwind e
fontes originais disponibilizados localmente para a captura offline.

| Elemento do original | Resultado / justificativa |
| --- | --- |
| Fundo escuro, superfícies, bordas discretas, detalhes dourados e cards em três colunas | Preservados; dourado das ações ajustado a `#e5b044`, conforme solicitado. |
| Indicadores e barra de filtros | Estrutura preservada; valores exclusivamente do agregado existente. Não se inventam faturamento, contagem de prontos para pagar ou tempo médio de espera. |
| Data única e atalhos de dia | Mantido o intervalo de datas funcional existente, com rótulos acessíveis e aplicação explícita dos filtros. |
| Comandas em atendimento, prontas e pagas | Preservados os estados reais da comanda e do atendimento, apresentados separadamente. “Fechada” não é convertida automaticamente em “Paga”. |
| Identificação sequencial `#CMD-2084` | Mantida identificação derivada do UUID real e acesso ao UUID completo. Não existe numeração sequencial nesse contrato. |
| Abrir comanda, editar itens, impressão fiscal, VIP, desconto e dados de fidelidade | Não adicionados: não há suporte correspondente no fluxo contratado. A ação principal existente continua sendo consultar a comanda. |
| Notificações, menu executivo amplo e operador do protótipo | Mantido o shell real do aplicativo, com suas rotas, usuário e seleção de filial. Não se criam menus ou identidades fictícias. |
| Sincronização a cada dez segundos e log de auditoria global | Não simulados. Mantidas atualização manual e atualização automática após operações financeiras. Histórico financeiro existente continua disponível. |
| Detalhes e painel de pagamentos | Adaptação visual nova: duas colunas no desktop e uma coluna em tablet/celular; cards de pessoas, serviços, informações e financeiro. |
| Valor Total e Valor Recebido | Destaque principal do financeiro. Recebido continua sendo pagamentos menos estornos; legado desconhecido aparece como “Não verificado”. No celular, resumo em uma coluna para acomodar valores. |

As imagens remotas do original não estão disponíveis na captura offline. Fontes
e ícones do original foram carregados de cópias temporárias; nenhuma dessas
dependências foi incorporada ao aplicativo. O aplicativo continua usando seus
ícones SVG locais e sua fonte configurada, com fallback do sistema nos testes
sem rede. Textos e valores das capturas da aplicação são fixtures **somente dos
testes**; nenhuma fixture foi adicionada à interface real.

## Validação executada

Executada em imagens Docker locais, com `--network none`, sem portas publicadas,
montando somente código/configuração selecionados como leitura. Não foram
montados arquivos `.env`. A instalação do Firefox usou o Dockerfile de testes
existente, com camada em cache. O download público de Tailwind/fontes para a
referência ocorreu separadamente, sem montar credenciais ou código da aplicação.

| Verificação | Resultado |
| --- | --- |
| Suíte frontend `node --test --test-reporter=dot tests/*.test.mjs` | Passou (126 testes). |
| TypeScript `tsc -b` | Passou. |
| Build Vite | Passou. |
| ESLint | Passou. |
| `comandas.browser.mjs` no Firefox | Passou. |
| `financeiro.browser.mjs` no Firefox | Passou. |
| Captura offline do HTML original | Passou, com limitação das imagens remotas descrita acima. |
| `git diff --check` | Passou; avisos locais de normalização LF/CRLF, sem erros de whitespace. |

Testes de interface exercitaram filtros, paginação, grade/lista, loading, vazio,
erros, troca de filial, perfil, Escape, restauração e contenção de foco. Foram
capturadas telas em 1440×1100, 900×1000 e 390×844, com verificação de ausência de
overflow horizontal no diálogo e nos tamanhos de listagem já cobertos pela suíte.

No financeiro, os cenários existentes passaram: soma insuficiente/excedente
bloqueada, confirmação explícita, métodos combinados em um único fechamento,
clique duplo, estornos históricos, atualização automática de detalhes e
indicadores, confirmação incerta/503 com replay da mesma chave e payload,
persistência indisponível/corrompida, 422, fechamento durante POST, quitação
anterior sem nova cobrança, total zero, atendimento não concluído, legado não
verificado, 403/404 e restrições dos quatro perfis. Nenhum pagamento avulso novo
foi introduzido. O código de idempotência, timeout e recuperação foi preservado.

## Evidências locais

Capturas e resultados desta execução foram retirados do versionamento.
Para o comportamento mantido, consulte [interface de comandas](comandas-interface.md).
Novas evidências devem ficar em `.local-qa/`, sem links Git para artefatos locais.

## Preservação e limites

Os 43 arquivos locais anteriores foram conferidos pelo manifesto SHA-256 da
preparação da branch: **43 presentes, zero conteúdos divergentes**. Nenhum reset,
clean, stash ou troca de branch foi usado nesta etapa. A referência foi apenas
lida e copiada para uma pasta temporária para captura.

O navegador foi real; a API dos testes foi simulada em loopback. Não foi repetida
a homologação integrada com FastAPI/PostgreSQL nem o timeout Axios real de 15 s.
Não havia ambiente integrado descartável em execução; provisioná-lo exigiria
preparar banco/schema. Nenhuma migração foi executada e nenhum acesso ao Supabase
foi feito. As garantias transacionais do backend permanecem as homologadas na
Etapa 3, sem mudança de implementação nesta etapa.

Não houve auditoria automatizada completa de acessibilidade nem teste em todos
os dispositivos reais. A cobertura desta entrega inclui teclado, rótulos,
feedback existente de erros, foco do diálogo, telas responsivas e inspeção visual.

Aguardando revisão do usuário antes de commit ou push.
