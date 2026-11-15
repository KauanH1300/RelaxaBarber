# Etapa 1 — separação de atendimento e comanda

> Documento histórico de implementação, mantido para revisão; descrições e
> pendências abaixo refletem sua etapa, não o estado atual do sistema.
> Referências técnicas atuais: [interface](comandas-interface.md),
> [contratos HTTP](financeiro-mvp-http.md), [transações](financeiro-mvp-servicos.md)
> e [persistência](financeiro-mvp-persistencia.md).
> Evidências de execução são locais e não integram a documentação versionada.


## Base preservada antes das edições

Branch inicial `feat/financeiro-comandas`, HEAD `292a974`. Foram inventariadas
11 modificações rastreadas e 23 entradas não rastreadas (diretórios expandidos
incluídos no manifesto). Cópia byte a byte dos 45 arquivos locais em
`C:\Users\kauan\AppData\Local\Temp\relaxabarber-etapa1-20261114-180831`,
com caminhos e SHA256 em `manifest.json`. A cópia é temporária e não é commit.
Branch criada posteriormente: `feat/comandas-fechamento-integral-atomico`.
Sem stash, commit, push, reset, clean ou substituição das mudanças anteriores.

Inventário das 11 modificações anteriores:

| Arquivo | Mudança existente | Evidência/risco |
| --- | --- | --- |
| backend/app/api/routes/financeiro.py | Documentação do histórico no GET | Etapa 11 relata testes locais; preservar contrato |
| backend/app/schemas/financeiro.py | DTOs e histórico aditivo | Etapa 11 relata testes locais; preservar serialização |
| backend/app/services/financeiro.py | Leitura ordenada do histórico sob lock | Etapa 11 relata testes locais; sobreposição com esta etapa |
| backend/tests/contracts/test_financeiro_http.py | Três testes de histórico/OpenAPI | Etapa 11 relata execução aprovada |
| docs/financeiro-mvp-http.md | Contrato do histórico e informação sobre revisão remota | Evidência documental, não comprovação atual do banco |
| frontend/package.json | Script dev chama node/vite diretamente | Alteração anterior às etapas 10/11; execução dev não validada aqui |
| frontend/src/assets/logo.png | Substituição binária da logo | Alteração anterior; preservar bytes, sem atribuir aprovação visual |
| frontend/src/pages/comandas/Comandas.css | Estilos financeiros | Relatórios locais anteriores; apresentação real depende de QA |
| frontend/src/pages/comandas/Comandas.tsx | Orientação sobre financeiro | Texto mantém semântica operacional antiga |
| frontend/src/pages/comandas/DetalheComanda.tsx | Integra painel financeiro e foco dos formulários | Evidência local anterior; rótulos ainda antigos |
| frontend/tests/comandas.browser.mjs | Mock GET financeiro | Evidência local anterior; não testa Supabase |

Inventário das 23 entradas não rastreadas anteriores:

| Entrada | Conteúdo e avaliação |
| --- | --- |
| backend/integration_tests/Dockerfile | Executor com pytest; construção requer dependência; não executado |
| backend/integration_tests/test_financeiro_historico.py | 15 cenários de histórico; etapa 11 relata aprovação PostgreSQL |
| backend/scripts/ | Seis scripts: qa_financeiro_login_leitura.py, qa_financeiro_persistencia_leitura.py, qa_financeiro_precondicoes.py, qa_financeiro_preservacao.py, qa_financeiro_retomada_leitura.py, seguranca_etapa13_leitura.py; acessam configuração/banco remoto; não executar nesta etapa |
| docs/financeiro-etapa10-interface.md | Interface local concluída; limitações de QA descritas, histórico ampliado na etapa seguinte |
| docs/financeiro-etapa11-historico.md | Relata 836 backend, 222 integração e 121 frontend aprovados; evidência histórica |
| docs/financeiro-etapa12-retomada.md | Retomada de QA real; não comprova prontidão atual |
| docs/financeiro-etapa12-validacao.md | Legado e cenários reais pendentes; não inferir quitação |
| docs/financeiro-etapa13-seguranca.md | Auditoria de segurança anterior; preservar evidência |
| docs/financeiro-etapa14-perfis.md | Validação real por perfis parcialmente pendente |
| docs/financeiro-etapa14-retomada.md | Lista operações manuais pendentes; não executar automaticamente |
| docs/qa-financeiro-20261113/ | Duas imagens e quatro JSON: fluxo-real, persistencia-supabase, preservacao-final/inicial; evidências de um ambiente anterior |
| docs/qa-perfis-20261113/ | Dois JSON de preservação; não equivalem a aprovação de todos os fluxos |
| frontend/src/pages/comandas/FinanceiroComanda.tsx | Painel funcional anterior com pagamentos separados e recuperação; não redesenhar nesta etapa |
| frontend/src/pages/comandas/HistoricoComanda.tsx | Histórico persistido e estornos associados; preservar |
| frontend/src/services/financeiro.ts | Transporte, centavos, permissões, estados e pendências; ajuste mínimo de estado necessário |
| frontend/tests/Dockerfile.browser | Executor Firefox; não construído nesta etapa |
| frontend/tests/financeiro.browser.mjs | Fluxo com API simulada; não comprova banco real |
| frontend/tests/financeiro.supabase.mjs | QA com operações reais; não executar |
| frontend/tests/financeiro.test.mjs | 11 testes locais com mocks; atualizar expectativa de comanda aberta concluída |
| frontend/tests/helpers/executarQaPerfis.cjs | Executor do QA remoto; não executar |
| frontend/tests/helpers/executarQaReal.cjs | Executor do QA remoto; não executar |
| frontend/tests/helpers/validarFrontend.cjs | Testes/build/lint offline, cópia dentro de container; adequado para esta etapa |
| frontend/tests/perfis.supabase.mjs | QA autenticado e operações reais; não executar |

Implementação presente não significa validação real concluída. Os relatórios de
QA por perfis ainda listam pendências. Nenhuma credencial ou arquivo .env foi
lido por esta implementação.

## Decisões de modelagem e compatibilidade

- Não criar coluna, enum ou migração. Atendimento continua com `concluido`;
  novas comandas permanecem `aberta`, sem preencher `data_fechamento`.
- Situação financeira continua independente: `aberto`, `fechado`, `nao_verificado`.
- O fechamento existente continua exigindo quitação e motivo para total zero.
  Para comanda aberta, grava estado `fechada` e data do registro financeiro na
  mesma transação do fechamento. Pagamento integral sozinho não fecha a comanda.
- Aceitar no serviço financeiro tanto comanda aberta concluída quanto o antigo
  estado fechado operacionalmente, mantendo bloqueios de legado não verificado,
  financeiro já fechado, cancelamento e atendimento não concluído.
- Não reclassificar registros antigos, não substituir datas históricas nem
  reparar registros durante GET ou replay. Fechamento financeiro existente
  permanece a evidência autoritativa de quitação; `status=fechada` histórico
  isoladamente não é prova de pagamento.
- Autorizações, ordem dos locks, fingerprint, idempotência, auditoria e
  restrições de estorno permanecem nos caminhos existentes.
- Frontend recebe apenas ajuste na função de habilitação por estado e seu teste,
  sem layout novo. Textos e resumo visual antigos ficam para a etapa de interface.

## Limites e próximos passos

Esta é uma base intermediária para revisão, não a entrega da regra atômica:
o endpoint de pagamentos ainda permite lançamentos parciais separados.
Não publicar isoladamente como implementação completa da política sem fiado.
Revisar a classificação dos históricos antes de qualquer reclassificação ou
migração. A etapa seguinte deverá reunir confirmação integral e fechamento e
impedir novas parciais isoladas, preservando replay das operações antigas.

A suíte PostgreSQL não foi executada: seu fixture recria schema e aplica a cadeia
de migrações, vedada nesta etapa. O teste de ativação foi atualizado para os novos
estados, mas a execução PostgreSQL e a prova de concorrência ficam pendentes.
Os testes SQLite usam contexto financeiro substituído para isolar a transação;
não comprovam locks PostgreSQL. Permissões e isolamento têm testes próprios.

## Arquivos desta etapa

- backend/app/services/agendamento.py: conclusão sem fechamento.
- backend/app/services/financeiro.py: aceita conclusão com comanda aberta e fecha
  a comanda somente na transação do fechamento financeiro quitado; preserva histórico anterior.
- backend/tests/regression/test_agendamentos.py: nova expectativa de conclusão.
- backend/tests/permissions/test_regras_financeiras.py: estados aceitos e rejeitados.
- backend/tests/persistence/test_estados_comanda.py: cinco casos novos de estados,
  quitação, replay, compatibilidade de data e rollback.
- backend/integration_tests/test_financeiro_ativacao.py: conclusão deixa aberta e sem data.
- backend/integration_tests/test_financeiro_http.py: substitui estado agora válido
  por comanda pendente incompatível no cenário de rejeição.
- backend/integration_tests/test_financeiro_servicos.py: mesma atualização de rejeição.
- backend/integration_tests/test_cancelamento_etapa_g.py: concorrência da conclusão
  espera comanda aberta e data de fechamento ausente.
- frontend/src/services/financeiro.ts: habilitação compatível com comanda aberta concluída.
- frontend/tests/financeiro.test.mjs: expectativa correspondente.
- Este relatório.

## Validação executada

Containers descartáveis, rede desativada, checkout somente leitura. Backend usa
pytest 8.4.2 já disponível em backend/.venv/lib/python3.12/site-packages via
PYTHONPATH; não foi instalada dependência. A imagem backend não contém pytest
por padrão. Não foram executados scripts de QA remoto nem carregado .env.

- Backend existente: `python -m pytest tests -q -p no:cacheprovider`:
  **839 aprovados**, 171,44 segundos. A coleta ocorreu antes da criação do novo
  arquivo; por isso os cinco casos adicionais foram executados separadamente.
- Novos casos: `python -m pytest tests/persistence/test_estados_comanda.py -q
  -p no:cacheprovider`: **5 aprovados**, 15,84 segundos. Total: **844 casos distintos**.
- Frontend: executor offline `validarFrontend.cjs`: **121 testes aprovados**,
  TypeScript, Vite build e ESLint com exit 0.
- `git diff --check`: aprovado.
- Integração PostgreSQL: **não executada**, pois requer migrações no fixture.
  Atualizar expectativas não equivale a comprovar execução ou concorrência.

Comparação SHA256 dos 45 arquivos preservados: apenas três receberam ajustes
adicionais nesta etapa (services/financeiro.py do backend, services/financeiro.ts
e tests/financeiro.test.mjs do frontend). Os demais 42 permaneceram byte a byte
iguais ao snapshot, inclusive package.json, logo, evidências QA e histórico.
Os demais arquivos desta etapa eram rastreados limpos ou foram criados agora.
