# Homologação final integrada do redesign Stitch

**Resultado: aprovado nos cenários executados no ambiente descartável.**
Data: 15/11/2026. Branch `feat/comandas-redesign-stitch`; HEAD `a69223b`.
Sem commit ou push. Este resultado substitui a pendência de integração registrada
em `comandas-homologacao-final-stitch.md`.

## Autorização e isolamento

O usuário autorizou explicitamente a exceção: executar as migrações existentes
**apenas no PostgreSQL descartável, isolado e sem rede**. Foi reutilizado o
provisionador existente `backend/integration_tests/homologacao_etapa3.py`, que
aplica as revisões existentes por suas funções `upgrade()` no banco de teste.
Não houve migração nova nem mudança de backend, contratos ou configuração real.

PostgreSQL 17: container exclusivo `rb-stitch-final-pg`, `--network none`, sem
portas publicadas, sem volumes persistentes, dados em tmpfs. FastAPI e Firefox
compartilharam exclusivamente seu namespace de rede. As imagens já eram locais.
Nenhum container normal da aplicação foi usado ou reiniciado.

Código/configurações foram montados como leitura, sem `.env`. Saída externa
comprovadamente bloqueada (`connect_ex=101`). A URL fixa de teste usa loopback,
porta 55432 e banco `relaxabarber_concorrencia_test`. O FastAPI executou como
`relaxabarber_dev_app`: **sem superusuário e sem bypass de RLS**, verificado em SQL.
Credenciais e JWT eram exclusivamente fictícios desse ambiente; tokens não
foram registrados nas evidências. Nenhum acesso ao Supabase.

## Cenários reais aprovados

| Cenário | Evidência observada |
| --- | --- |
| Ciclo completo pela interface | Criar agendamento, registrar chegada, iniciar, concluir, consultar comanda e receber/fechar. Escritas pela UI real. |
| Estados separados | Concluir atendimento mantém comanda aberta e data de fechamento nula; recebimento confirmado fecha a comanda. |
| PIX100 + dinheiro200 | Um fechamento com dois recebimentos; total e recebido R$ 300; saldo zero. |
| Soma insuficiente | UI bloqueia; requisição direta rejeitada com 409, sem pagamento persistido. |
| Clique duplo e replay | Um envio pela UI; replay HTTP com a mesma chave/payload retorna 200 sem duplicação. |
| Timeout real | Proxy atrasa a resposta por 17 s após commit; Axios expira em 15 s. Recuperação mantém chave/payload e apenas um pagamento. |
| 503 antes do backend | Nenhum pagamento inicial; recuperação original confirma exatamente uma vez. |
| Atualização automática | Detalhes passam a Fechada, recebido passa a R$ 300, abertas passam a zero no período testado, sem recarga manual. |
| ADMIN, RECEPCAO, BARBEIRO e BARBEIRO_CHEFE | Fechamentos reais pelos quatro perfis. |
| Outro profissional | Barbeiro e barbeiro chefe recebem 404 em leitura e escrita; zero pagamentos nas comandas de acesso indevido. |
| Outra filial | Contexto incorreto rejeitado; não se lê nem fecha comanda de outra filial pelo ID apresentado no escopo errado. |
| Quitação histórica verificada | Finaliza com lista vazia, preserva pagamento anterior e data operacional histórica. |
| Legado não verificado | Não presume recebimento; UI sem formulário de cobrança, requisição de fechamento retorna 409. |

Persistência final, consultada com o login restrito: **11 comandas, 10 controles,
9 pagamentos e 8 fechamentos financeiros**. Um pagamento é a fixture histórica;
os oito restantes correspondem a sete novas comandas, uma com dois métodos.
As duas comandas usadas nas tentativas indevidas ficaram abertas, sem pagamento
e sem data de fechamento. O legado preservou seu estado histórico sem adquirir
comprovação financeira. Dez POSTs partiram da UI, incluindo duas recuperações;
o 503 injetado antes do envio não alcançou o backend. Sem erros HTTP 500 no log.

## Layout, usabilidade e comparação visual

React/Vite e Firefox reais com dados fictícios persistidos no PostgreSQL
descartável. Verificações em **1440×1100, 900×1000, 390×844 e 320×740**:

- Página e diálogo sem overflow horizontal.
- Resumo financeiro visível abaixo do cabeçalho fixo ao rolar.
- Campo de valor sem elemento sobreposto no centro; formulários acessíveis.
- Histórico expansível, rolagem e conteúdo do modal acessíveis.
- Tab/Shift+Tab contidos, ciclo completo do foco, Escape com restauração e
  abertura por Enter.
- Painel, valores e estados atualizados com respostas reais.

Comparação visual feita com `ref/comandas.html` e a captura offline do original
produzida na fase anterior, com fontes/Tailwind originais. Cores, superfícies,
indicadores, filtros e grade mantêm sua linguagem visual. Diferenças deliberadas:
botões `#e5b044`; shell real existente; filtros de intervalo; UUIDs; estados
operacional e financeiro separados; agregados indisponíveis identificados; sem
VIP, desconto, impressão fiscal ou sincronização periódica fictícios. O modal
financeiro é uma adaptação: o original não fornece essa tela.

O celular usa uma coluna, e o título quebra em 320 px sem cobrir o botão de
fechar. Não foram identificados novos defeitos da aplicação nos cenários reais.
Permanece a limitação visual de imagens remotas ausentes no original offline e
fonte de fallback na aplicação sem rede. Os screenshots não são de produção.

## Correções e tentativas

A correção de acessibilidade identificada na fase anterior — excluir controles
internos de `<details>` recolhidos do ciclo do foco — passou também na integração
real, nas quatro larguras. Nenhuma nova correção de aplicação foi necessária.

Duas falhas do executor foram corrigidas, mantendo todas as verificações:

1. Normalizar explicitamente o espaço não separável da moeda brasileira na
   comparação de “Valor Recebido”. O backend/UI já exibiam R$ 300 corretamente.
2. Aguardar a nova requisição chegar ao proxy e a consulta pós-503 terminar antes
   de guardar sua chave. O aviso de pendência aparece antes desse término e
   permitia ao teste guardar a chave da operação anterior.

As duas tentativas incompletas estão em `integrada/tentativa1*` e `tentativa2*`.
Após cada falha, somente o schema/fixtures do PostgreSQL descartável foram
recriados, e a suíte inteira foi repetida. `integrada/homologacao.json`, com
`resultado: aprovado`, é o resultado definitivo. Uma captura adicional precisou
usar a origem local 5173 já permitida pelo CORS; nenhuma configuração foi alterada.

## Checks e evidências

126 testes frontend, TypeScript (`tsc -b`), build Vite e ESLint passaram. O lint
foi repetido após as correções exclusivas do executor. A suíte integrada também
passou por completo; não substituiu o backend por respostas simuladas. O proxy
apenas injeta atraso/falha de transporte nos cenários especificados.

- [Cenários e resultado definitivo](qa-comandas-homologacao-final/integrada/homologacao.json)
- [Log do navegador real](qa-comandas-homologacao-final/integrada/browser-real-checks.txt)
- [Persistência SQL final](qa-comandas-homologacao-final/integrada/persistencia-final.txt)
- [Checks frontend](qa-comandas-homologacao-final/integrada/frontend-checks.txt) e [lint final](qa-comandas-homologacao-final/integrada/lint-final.txt)
- [Isolamento PostgreSQL](qa-comandas-homologacao-final/integrada/isolamento-pg.txt), [executores](qa-comandas-homologacao-final/integrada/isolamento-executores.txt) e [sem .env/sem saída](qa-comandas-homologacao-final/integrada/sem-env-sem-saida.txt)
- [Referência original](qa-comandas-homologacao-final/stitch-original-desktop.png)
- Painel real: [desktop](qa-comandas-homologacao-final/integrada/painel-real-topo-desktop.png), [tablet](qa-comandas-homologacao-final/integrada/painel-real-topo-tablet.png), [celular](qa-comandas-homologacao-final/integrada/painel-real-topo-celular.png)
- Detalhes reais: [desktop](qa-comandas-homologacao-final/integrada/detalhe-real-desktop.png), [tablet](qa-comandas-homologacao-final/integrada/detalhe-real-tablet.png), [celular](qa-comandas-homologacao-final/integrada/detalhe-real-celular.png)
- Financeiro real: [celular](qa-comandas-homologacao-final/integrada/financeiro-real-celular.png), [320 px](qa-comandas-homologacao-final/integrada/financeiro-real-celular-estreito.png)
- [Fechada com total/recebido](qa-comandas-homologacao-final/integrada/fechada-real-desktop.png) e [histórico PIX100 + dinheiro200](qa-comandas-homologacao-final/integrada/pagamentos-combinados-reais.png)

## Arquivos e preservação

Nesta retomada foram alterados somente o executor
`frontend/tests/homologacao-etapa4.browser.mjs`, este relatório, a nota de
atualização no relatório parcial e novas evidências em
`docs/qa-comandas-homologacao-final/integrada/`.

Antes da retomada, 96 arquivos locais pendentes foram copiados com manifesto
SHA-256 para a pasta indicada por `%TEMP%/relaxabarber-final-integrada-pointer.txt`.
Todos foram preservados, exceto as atualizações intencionais do executor e da
nota do relatório parcial, cujas versões anteriores estão no snapshot. Os 43
arquivos originais permanecem idênticos por SHA-256. Nenhum backend ou contrato
foi alterado. A correção de foco em `DetalheComanda.tsx` já fazia parte do estado
local recebido nesta retomada.

O ambiente descartável foi encerrado e removido após a coleta das evidências;
o PostgreSQL em tmpfs não foi mantido. Nenhum container normal foi interrompido.
Sem commit, push ou merge; aguardando revisão do usuário.

## Limites

Cobertura dos cenários listados, sem auditoria automatizada completa de
acessibilidade ou dispositivos físicos. Não houve transação com gateway bancário:
o recebimento continua sendo confirmação explícita do operador, conforme o
contrato existente. A suíte ampla de concorrência/backend da Etapa 3 não foi
reexecutada, pois o backend não mudou.
