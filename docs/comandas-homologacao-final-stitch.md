# Homologação final Stitch — execução parcial, integração pendente

> Atualização: após a exceção autorizada pelo usuário, a homologação integrada
> foi concluída. Consulte [o relatório definitivo](comandas-homologacao-final-integrada-stitch.md).
> O conteúdo abaixo preserva o registro da primeira execução parcial.

Data: 15/11/2026. Branch: `feat/comandas-redesign-stitch`, HEAD `a69223b`.

**A homologação integrada ainda não foi executada nem aprovada.** O requisito
de não executar migrações foi respeitado. Não há PostgreSQL de homologação
preparado nem dump de schema disponível no projeto. O provisionador existente
`backend/integration_tests/homologacao_etapa3.py` executa a cadeia de migrações;
por isso ele não foi executado. Os containers normais da aplicação não foram
usados, alterados ou reiniciados.

Está pendente a definição do usuário entre indicar um dump somente de schema
homologado e autorizar excepcionalmente as migrações existentes no PostgreSQL
descartável sem rede. Não foi criado um schema simplificado com `create_all`,
pois isso não reproduziria necessariamente triggers, constraints, grants e
permissões financeiras da homologação anterior.

## Preservação

Antes dos testes foram copiados e registrados por SHA-256 os **63 arquivos
locais pendentes** nesta retomada, incluindo os 43 originais, o redesign e as
evidências anteriores. Snapshot fora do repositório, identificado por
`%TEMP%/relaxabarber-homolog-final-pointer.txt`; manifesto `manifest.xml` na
pasta apontada. A referência `ref/comandas.html` também foi copiada.

A única mudança em arquivo preexistente nesta execução é a correção de foco
descrita abaixo em `DetalheComanda.tsx`; sua versão anterior permanece no
snapshot. Os 43 arquivos locais originais continuam intactos. Nenhuma mudança
em backend, contratos financeiros, dependências, banco ou configuração real.
Sem commit, push, merge, reset, clean, stash ou troca de branch.

## Defeito encontrado e corrigido

**Ciclo do foco no modal:** com seções recolhidas, o Firefox podia manter
retângulos de layout de descendentes de `<details>` fechados. O filtro de
elementos navegáveis aceitava controles invisíveis e tentava focá-los ao usar
Shift+Tab no primeiro botão; o foco não retornava corretamente ao último controle
visível. O filtro agora exclui os descendentes de seções recolhidas, mantendo
somente o `<summary>` imediato de cada seção visível.

Correção limitada à acessibilidade do redesign, sem alterar consultas,
pagamentos, idempotência ou recuperação. O novo teste falhou antes da correção
no ciclo Shift+Tab/Tab e passou depois nas quatro larguras abaixo. A verificação
de restauração de foco usa abertura efetiva por Enter, evitando confundir
`element.click()` programático com um acionador realmente focado.

## Arquivos desta execução

| Arquivo | Mudança |
| --- | --- |
| `frontend/src/pages/comandas/DetalheComanda.tsx` | Exclusão de controles de seções recolhidas do ciclo de foco. |
| `frontend/tests/homologacao-etapa4.browser.mjs` | Novo executor que estende a suíte integrada existente com verificações visuais, rolagem e teclado; também oferece `--layout-simulado` para verificar esses cenários sem banco. Não cria schema nem executa migrações. |
| `docs/qa-comandas-homologacao-final/` | Logs e capturas desta execução. |
| Este relatório | Resultados e pendências explícitas. |

## Validações concluídas

Todas as execuções de testes usaram containers novos com `--network none`,
sem portas publicadas. Somente código/configurações selecionados foram montados,
como leitura; nenhum `.env` foi montado. O navegador foi Firefox real, frontend
React/Vite real e **API simulada em loopback**.

| Verificação | Resultado |
| --- | --- |
| 126 testes frontend | Passaram. |
| TypeScript `tsc -b` | Passou. |
| Build Vite | Passou. |
| ESLint | Passou. |
| Suíte de comandas no Firefox | Passou: filtros, paginação, estados, grade/lista, acesso, mobile, Escape e restauração de foco. |
| Suíte financeira no Firefox | Passou: métodos combinados, soma exata, confirmação, clique duplo, replay, pendências, estornos históricos, quitação anterior, atualização, erros, perfis e filial simulados. |
| Verificações adicionais de layout/teclado | Passaram em 1440×1100, 900×1000, 390×844 e 320×740. |

Verificações adicionais: ausência de overflow horizontal na página e no modal,
resumo financeiro visível abaixo do cabeçalho ao rolar, centro do campo de valor
sem sobreposição, histórico expansível, rolagem, Tab e Shift+Tab contidos, ciclo
do último para o primeiro controle, Escape com foco restaurado e Enter para
reabrir. Não foi encontrada outra divergência funcional de layout nesses testes.

## Comparação visual

Nova captura do HTML original, com o Tailwind e as fontes originais já disponíveis
em cópias temporárias, em navegador sem rede. A cópia do HTML foi conferida por
hash contra `ref/comandas.html`. Imagens remotas do original continuam ausentes.

Comparação visual: fundo, cartões, dourado, hierarquia e composição geral se
mantêm coerentes com o original. A interface real preserva o shell e filtros
existentes, UUIDs reais e estados separados. VIP, desconto, impressão fiscal,
faturamento agregado indisponível e sincronização periódica do protótipo não
foram inventados. A referência não possui tela detalhada de pagamento; o modal
é uma adaptação da mesma linguagem visual. Em 320 px o título do modal quebra
em duas linhas e o resumo fica em uma coluna, sem sobreposição dos valores.

Capturas desta execução usam **fixtures de testes simulados**, não dados de
produção e não resultados de PostgreSQL real.

- [Checks frontend/TypeScript/build/lint](qa-comandas-homologacao-final/frontend-checks.txt)
- [Saída resumida das suítes de navegador com API simulada](qa-comandas-etapa4/browser-checks.txt)
- [Verificações ampliadas de layout/teclado](qa-comandas-homologacao-final/layout-simulado-checks.txt)
- [Referência original](qa-comandas-homologacao-final/stitch-original-desktop.png)
- [Detalhes desktop](qa-comandas-homologacao-final/detalhe-simulado-desktop.png)
- [Financeiro tablet](qa-comandas-homologacao-final/financeiro-simulado-tablet.png)
- [Financeiro celular](qa-comandas-homologacao-final/financeiro-simulado-celular.png)
- [Financeiro 320 px](qa-comandas-homologacao-final/financeiro-simulado-celular-estreito.png)

Para versionamento, a saída resumida do navegador foi consolidada no arquivo da
Etapa 4 vinculado acima: ele é idêntico byte a byte ao
`qa-comandas-homologacao-final/browser-simulado-checks.txt` desta execução.
O segundo arquivo continua preservado localmente, sem ser proposto para commit.
As evidências adicionais de layout/teclado e a homologação integrada mantêm
seus próprios resultados; a consolidação não representa uma nova execução.

## Pendente para aprovação integrada

Após definir a origem autorizada do schema: criar PostgreSQL em tmpfs,
`--network none`, sem portas e sem volumes da aplicação; executar FastAPI como
runtime sem superusuário/bypass RLS; executar React e Firefox no mesmo namespace
isolado. A nova suíte integrada reutiliza os cenários anteriores de ciclo
completo pela UI, PIX100 + dinheiro200, timeout Axios real de 15 s após commit,
replay sem duplicação, quatro perfis, outra filial e atualização automática,
acrescentando a bateria visual/teclado. **Esses cenários reais ainda não foram
executados nesta retomada.** Não se atribui a testes simulados comprovação de
persistência, atomicidade ou isolamento reais.

Não houve migração nem acesso ao Supabase. A homologação final permanece pendente
da preparação autorizada do schema e da execução integrada. Nenhuma publicação.
