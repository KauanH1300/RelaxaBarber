# Etapa 11 — histórico financeiro persistente

> Documento histórico de implementação, mantido para revisão; descrições e
> pendências abaixo refletem sua etapa, não o estado atual do sistema.
> Referências técnicas atuais: [interface](comandas-interface.md),
> [contratos HTTP](financeiro-mvp-http.md), [transações](financeiro-mvp-servicos.md)
> e [persistência](financeiro-mvp-persistencia.md).
> Evidências de execução são locais e não integram a documentação versionada.


Implementação local concluída na branch `feat/financeiro-comandas`. O bloqueio de
histórico e estorno de pagamentos anteriores descrito no relatório da etapa 10 foi
resolvido. Nenhuma operação foi realizada no Supabase.

## Arquivos desta etapa

Modificados:

- `backend/app/services/financeiro.py`: DTOs imutáveis mínimos e leitura ordenada dos registros persistidos dentro da consulta já autorizada.
- `backend/app/schemas/financeiro.py`: schemas do histórico, acrescentados à resposta do resumo.
- `backend/app/api/routes/financeiro.py`: documentação da resposta ampliada, sem nova rota.
- `backend/tests/contracts/test_financeiro_http.py`: três testes novos de contrato, serialização, legado e OpenAPI.
- `frontend/src/services/financeiro.ts`: tipos do histórico e associação dos estornos com cálculo exato em centavos por pagamento.
- `frontend/src/pages/comandas/FinanceiroComanda.tsx`: uso exclusivo do GET como fonte do histórico, seleção de pagamentos antigos e recarga após POSTs.
- `frontend/tests/financeiro.test.mjs`: quatro testes novos de histórico, reabertura, renderização e preservação da pendência.
- `frontend/tests/comandas.browser.mjs`: mock financeiro atualizado para o contrato atual.
- `frontend/tests/helpers/validarFrontend.cjs`: opção para executar os cenários Firefox isolados.
- `docs/financeiro-mvp-http.md`: contrato final atualizado.

Criados:

- `frontend/src/pages/comandas/HistoricoComanda.tsx`: pagamentos, valores estornados/líquidos, estornos associados, motivos, datas e identificadores.
- `backend/integration_tests/test_financeiro_historico.py`: 15 cenários PostgreSQL/HTTP novos.
- `frontend/tests/financeiro.browser.mjs`: fluxo interativo com Firefox, API fictícia e dados mantidos pelo servidor simulado entre reaberturas.
- `backend/integration_tests/Dockerfile`: executor de testes com pytest sobre a imagem backend local.
- `frontend/tests/Dockerfile.browser`: executor Firefox sobre a imagem frontend local.
- Este relatório.

Os demais arquivos já alterados ou não rastreados no início da etapa foram
preservados, inclusive o relatório da etapa 10 e os ajustes anteriores de layout.

## Contrato HTTP final

O mesmo `GET /comandas/{id}/financeiro`, com Bearer e `filial_id` opcional, mantém
todos os campos atuais. `pagamentos` e `estornos` continuam sendo strings de
somatórios, nunca listas. O único acréscimo é:

```json
{
  "historico": {
    "pagamentos": [
      {
        "id": "33333333-3333-4333-8333-333333333333",
        "valor": "10.00",
        "forma": "pix",
        "recebido_em": "2026-11-13T13:00:00Z",
        "registrado_em": "2026-11-13T13:01:00Z"
      }
    ],
    "estornos": [
      {
        "id": "66666666-6666-4666-8666-666666666666",
        "pagamento_id": "33333333-3333-4333-8333-333333333333",
        "valor": "2.00",
        "motivo": "Correção de recebimento",
        "efetivado_em": "2026-11-13T13:02:00Z",
        "registrado_em": "2026-11-13T13:03:00Z"
      }
    ]
  }
}
```

Cada lista é completa para a comanda autorizada e ordenada por
`registrado_em ASC, id ASC`. Datas efetivas retroativas não mudam essa ordem.
Dinheiro continua textual com duas casas e datas são normalizadas para UTC.
O resumo autoritativo continua sendo calculado pelos serviços existentes.

Não são retornados dados ou IDs de operadores, credenciais, fingerprints ou
chaves de idempotência no histórico. Os DTOs dos POSTs não foram alterados.
Para legado, as duas listas são vazias e os somatórios, líquido e saldo continuam
null: isso não afirma dívida ou quitação.

O histórico é materializado da persistência PostgreSQL sob o mesmo lock
compartilhado da consulta original. As escritas financeiras pelos serviços ficam
serializadas com essa leitura. Não há commit, flush, alteração de dados, mudança
de transação de escrita ou alteração das regras de idempotência.

## Autorização

O histórico é consultado somente após `_contexto` autorizar e bloquear a comanda,
revalidando usuário, perfil, empresa, filial e vínculo conforme as regras atuais.
ADMIN e RECEPCAO mantêm o escopo existente de filial; BARBEIRO e BARBEIRO_CHEFE
continuam restritos às próprias comandas. A query `filial_id` apenas restringe o
recurso e não o transfere de filial.

Recurso inexistente e recurso fora do escopo mantêm o 404 uniforme, sem histórico
parcial ou valores. Credencial inválida/inatividade seguem a autenticação atual.
Estorno permanece exclusivo ADMIN e é revalidado pelo backend.

## Integração frontend

- Pagamentos anteriores aparecem ao carregar e ao reabrir os detalhes.
- Cada pagamento mostra recebido, estornado, líquido, forma, datas e seus estornos com motivo e identificadores.
- ADMIN seleciona pagamentos do histórico com líquido positivo; pagamentos totalmente estornados ficam fora da seleção.
- A validação local considera todos os estornos carregados. O backend recalcula e valida o limite sob lock antes de gravar.
- Pagamento, estorno e fechamento confirmados invalidam os valores anteriores e recarregam resumo e histórico juntos.
- Não há lista local paralela nem inclusão otimista do retorno do POST, evitando duplicações entre replay e GET.
- Uma pendência incerta permanece separada do histórico. Consultar o GET não a apaga, mesmo que a gravação já apareça nele. O replay conserva exatamente chave, payload e data efetiva originais.
- O financeiro fechado mantém o histórico visível e bloqueia novas movimentações. Legado continua bloqueado.
- Em 403, o interceptor existente revalida as filiais e desmonta os detalhes. Em 404, a consulta mostra a mensagem genérica, sem histórico. Essa política foi preservada e validada no navegador.

## Validação realizada

| Verificação | Resultado |
| --- | --- |
| Backend completo, incluindo os contratos novos | **836 aprovados** |
| Integração PostgreSQL financeira e regressão | **222 cenários distintos aprovados** |
| Novos cenários PostgreSQL de histórico | **15 aprovados** |
| Frontend, incluindo quatro testes novos nesta etapa | **121 aprovados** |
| TypeScript `tsc -b` | Aprovado |
| Produção `vite build` | Aprovado |
| Lint `eslint .` | Aprovado |
| Firefox — suíte existente de comandas | Aprovada |
| Firefox — novo fluxo financeiro | Aprovado |
| `git diff --check` | Aprovado |

A primeira execução de integração teve 221 aprovações e uma falha na fixture do
empate de timestamps: o trigger de auditoria substituía o instante informado por
`clock_timestamp()`. A fixture foi corrigida exclusivamente no banco descartável,
desabilitando o trigger de carimbo durante sua preparação e reabilitando-o antes
da consulta HTTP. Constraints e autorização runtime permanecem reais. Os 15
cenários novos foram então reexecutados e aprovados, completando os 222 cenários
distintos. Não houve alteração no código de produção após essa execução.

A integração cobriu quatro perfis, reabertura em novas sessões PostgreSQL,
pagamentos múltiplos, estornos parciais/múltiplos, fechamento, desempate por UUID,
isolamento entre comandas e filial, revogação de acesso, legado, GET sem SQL de
escrita ou commit e replay após perda de confirmação sem duplicação.

O Firefox validou a interação real dos formulários: pagamentos parcial/integral,
seleção de pagamento antigo, múltiplos estornos, confirmações, bloqueio após
fechamento, cliques repetidos, pendência após 503, consulta e reabertura antes de
replay, igualdade da chave e do payload no retry, ausência de duplicação visual,
legado, 403/404, quatro perfis, restrição de outros profissionais, foco dentro do
diálogo e largura de 390 px sem rolagem horizontal no diálogo.

### Isolamento e reprodução

As imagens locais de execução foram preparadas com pytest e Firefox somente
para testes; os manifests e dependências da aplicação não foram alterados.
O download desses executores ocorreu durante o build das imagens. Todas as
suítes foram executadas sem rede externa.

Backend e frontend foram montados somente leitura nos containers. O frontend
foi copiado para uma área efêmera interna antes dos checks. O PostgreSQL 17 foi
criado em `rb-etapa11-pg`, `network none`, porta interna 55432, **sem portas
publicadas**, dados em tmpfs e base `relaxabarber_concorrencia_test`. O executor
compartilhou somente a rede desse container. O conftest validou o destino fixo
antes de recriar o schema e executar a cadeia real de migrations nesse banco
descartável. As requisições HTTP usaram JWT e login PostgreSQL runtime real,
sem superuser/BYPASSRLS. Nenhum teste executou migrations ou DML no Supabase.

Comandos das suítes backend, dentro do executor em `/app`:

```text
python -m pytest tests -q -p no:cacheprovider
python -m pytest integration_tests/test_financeiro_historico.py integration_tests/test_financeiro_http.py integration_tests/test_financeiro_ativacao.py integration_tests/test_financeiro_servicos.py integration_tests/test_financeiro_persistencia.py integration_tests/test_cancelamento_etapa_g.py integration_tests/test_concorrencia.py -q -p no:cacheprovider
python -m pytest integration_tests/test_financeiro_historico.py -q -p no:cacheprovider
```

Frontend: `node /source/tests/helpers/validarFrontend.cjs`; navegador:
o mesmo executor com `--browser`. As imagens de testes são reproduzíveis pelos
Dockerfiles adicionados, usando as imagens locais do projeto como base.

## Limitações e preservação

Não há pendência funcional desta etapa. O histórico completo por comanda não é
paginado; comandos com volumes excepcionalmente altos podem exigir paginação
em evolução futura. O painel não cria um histórico global.

A recuperação de intenções continua usando `sessionStorage`, como na etapa 10:
não há garantia de recuperação após fechar a aba, limpar o armazenamento ou
mudar de dispositivo. Esta etapa não altera essa política, nem transforma uma
consulta de histórico em confirmação automática de uma intenção.

`frontend/package.json` e `frontend/src/assets/logo.png` foram preservados byte a
byte, com os mesmos SHA256 do início:

- package.json: `E3894A862473B3CC1E775E75F4D1333A92844A4D9376B13D7F40ACB4A4FB52B1`
- logo.png: `5744331DF85257A3E1D70A2B760C4C243A86DCA5DD2B3C62D1B1F2794CF8DF40`

Mesma branch, sem `git add`, commit, push, merge ou rebase; alterações locais
anteriores preservadas. Sem nova migration, alteração de modelos/schema,
`.env`, `DATABASE_URL`, dados financeiros remotos ou novas dependências de
aplicação. Os containers e as imagens exclusivos desta validação foram removidos;
as imagens locais preexistentes foram preservadas.
